"""Defines the models used with the API application.

These models are used in the REST definitions.
"""
import logging
from datetime import datetime

from django.db import models, transaction
from django.db.models import Q
from django.utils.translation import gettext as _

from api import messages
from api.connresult.model import JobConnectionResult, TaskConnectionResult
from api.details_report.model import DetailsReport
from api.inspectresult.model import JobInspectionResult, TaskInspectionResult
from api.scan.model import (
    DisabledOptionalProductsOptions,
    ExtendedProductSearchOptions,
    Scan,
    ScanOptions,
)
from api.scantask.model import ScanTask
from api.source.model import Source

logger = logging.getLogger(__name__)


class ScanJob(models.Model):
    """The scan job captures all sources and scan tasks for a scan."""

    JOB_RUN = 0
    JOB_TERMINATE_PAUSE = 1
    JOB_TERMINATE_CANCEL = 2
    JOB_TERMINATE_ACK = 3

    # all job types
    scan_type = models.CharField(
        max_length=12,
        choices=ScanTask.SCANTASK_TYPE_CHOICES,
        default=ScanTask.SCAN_TYPE_INSPECT,
    )
    status = models.CharField(
        max_length=20,
        choices=ScanTask.STATUS_CHOICES,
        default=ScanTask.CREATED,
    )
    status_message = models.TextField(
        null=True, default=_(messages.SJ_STATUS_MSG_CREATED)
    )
    options = models.OneToOneField(ScanOptions, null=True, on_delete=models.CASCADE)
    report_id = models.IntegerField(null=True)
    start_time = models.DateTimeField(null=True)
    end_time = models.DateTimeField(null=True)

    # all scan job types
    scan = models.ForeignKey(
        Scan, related_name="jobs", null=True, on_delete=models.SET_NULL
    )
    sources = models.ManyToManyField(Source)
    connection_results = models.OneToOneField(
        JobConnectionResult, null=True, on_delete=models.CASCADE
    )

    # only inspection job
    inspection_results = models.OneToOneField(
        JobInspectionResult, null=True, on_delete=models.CASCADE
    )

    details_report = models.OneToOneField(
        DetailsReport, null=True, on_delete=models.CASCADE
    )

    class Meta:
        """Metadata for model."""

        verbose_name_plural = _(messages.PLURAL_SCAN_JOBS_MSG)
        ordering = ["-id"]

    def copy_scan_disabled_product_options(self):
        """Copy scan disabled products options."""
        new_disabled_optional_products = None
        if (
            self.scan
            and self.scan.options
            and self.scan.options.disabled_optional_products
        ):
            old_disabled_optional_products = (
                self.scan.options.disabled_optional_products
            )
            new_disabled_optional_products = (
                DisabledOptionalProductsOptions.objects.create(
                    jboss_eap=old_disabled_optional_products.jboss_eap,
                    jboss_fuse=old_disabled_optional_products.jboss_fuse,
                    jboss_brms=old_disabled_optional_products.jboss_brms,
                    jboss_ws=old_disabled_optional_products.jboss_ws,
                )
            )
        return new_disabled_optional_products

    def copy_scan_extended_product_options(self):
        """Copy extended product search to the job."""
        new_extended_products = None
        if (
            self.scan
            and self.scan.options
            and self.scan.options.enabled_extended_product_search
        ):
            old_extended_products = self.scan.options.enabled_extended_product_search
            new_extended_products = ExtendedProductSearchOptions.objects.create(
                jboss_eap=old_extended_products.jboss_eap,
                jboss_fuse=old_extended_products.jboss_fuse,
                jboss_brms=old_extended_products.jboss_brms,
                jboss_ws=old_extended_products.jboss_ws,
            )
            if old_extended_products.search_directories:
                new_extended_products.search_directories = (
                    old_extended_products.search_directories
                )

        return new_extended_products

    def copy_scan_options(self):
        """Copy scan options to the job."""
        scan = self.scan
        if scan is not None:
            self.sources.add(*scan.sources.all())
            self.scan_type = scan.scan_type
            if scan.options is not None:
                disable_options = self.copy_scan_disabled_product_options()
                extended_search = self.copy_scan_extended_product_options()
                scan_job_options = ScanOptions.objects.create(
                    max_concurrency=scan.options.max_concurrency,
                    disabled_optional_products=disable_options,
                    enabled_extended_product_search=extended_search,
                )
                self.options = scan_job_options
            self.save()

    def log_current_status(self, show_status_message=False, log_level=logging.INFO):
        """Log current status of task."""
        if show_status_message:
            message = (
                f"STATE UPDATE ({self.status})."
                f"  Additional State information: {self.status_message}"
            )
        else:
            message = f"STATE UPDATE ({self.status})"

        self.log_message(message, log_level=log_level)

    def log_message(self, message, log_level=logging.INFO):
        """Log a message for this job."""
        elapsed_time = self._compute_elapsed_time()
        actual_message = (
            f"Job {self.id:d}"
            f" ({self.scan_type}, elapsed_time: {elapsed_time:.0f}s) - "
        )
        actual_message += message
        logger.log(log_level, actual_message)

    def calculate_counts(self, connect_only=False):
        """Calculate scan counts from tasks.

        :param connect_only: counts should only include
        connection scan results
        :return: systems_count, systems_scanned,
        systems_failed, systems_unreachable
        """
        self.refresh_from_db()
        if self.status in (ScanTask.CREATED, ScanTask.PENDING):
            return None, None, None, None, None

        system_fingerprint_count = 0

        (
            connection_systems_count,
            connection_systems_scanned,
            connection_systems_failed,
            connection_systems_unreachable,
        ) = self._calculate_counts(ScanTask.SCAN_TYPE_CONNECT)
        if self.scan_type == ScanTask.SCAN_TYPE_CONNECT or connect_only:
            systems_count = connection_systems_count
            systems_scanned = connection_systems_scanned
            systems_failed = connection_systems_failed
            systems_unreachable = connection_systems_unreachable
        else:
            (
                _,
                inspect_systems_scanned,
                inspect_systems_failed,
                inspect_systems_unreachable,
            ) = self._calculate_counts(ScanTask.SCAN_TYPE_INSPECT)
            systems_count = connection_systems_count
            systems_scanned = inspect_systems_scanned
            systems_failed = inspect_systems_failed + connection_systems_failed
            systems_unreachable = (
                inspect_systems_unreachable + connection_systems_unreachable
            )
        self.refresh_from_db()
        if self.report_id and self.details_report:
            self.details_report.refresh_from_db()

            if self.details_report.deployment_report:

                system_fingerprint_count = (
                    self.details_report.deployment_report.system_fingerprints.count()
                )

        return (
            systems_count,
            systems_scanned,
            systems_failed,
            systems_unreachable,
            system_fingerprint_count,
        )

    def _calculate_counts(self, scan_type):
        """Calculate scan counts from tasks.

        :return: systems_count, systems_scanned,
        systems_failed, systems_unreachable
        """
        systems_count = 0
        systems_scanned = 0
        systems_failed = 0
        systems_unreachable = 0
        tasks = self.tasks.filter(scan_type=scan_type).order_by("sequence_number")
        for task in tasks:
            systems_count += task.systems_count
            systems_scanned += task.systems_scanned
            systems_failed += task.systems_failed
            systems_unreachable += task.systems_unreachable
        return systems_count, systems_scanned, systems_failed, systems_unreachable

    def _log_stats(self, prefix):
        """Log stats for scan."""
        (
            systems_count,
            systems_scanned,
            systems_failed,
            systems_unreachable,
            system_fingerprint_count,
        ) = self.calculate_counts()

        message = (
            f"{prefix} Stats:"
            f" systems_count={systems_count:d},"
            f" systems_scanned={systems_scanned:d},"
            f" systems_failed={systems_failed:d},"
            f" systems_unreachable={systems_unreachable:d},"
            f" system_fingerprint_count={system_fingerprint_count:d}"
        )
        self.log_message(message)

    def _compute_elapsed_time(self):
        """Compute elapsed time."""
        if self.start_time is None:
            elapsed_time = 0
        else:
            elapsed_time = (datetime.utcnow() - self.start_time).total_seconds()
        return elapsed_time

    @transaction.atomic
    def queue(self):  # noqa: C901
        """Queue the job to run.

        Change job state from CREATED TO PENDING.
        """
        self.copy_scan_options()

        target_status = ScanTask.PENDING
        has_error = self.validate_status_change(target_status, [ScanTask.CREATED])
        if has_error:
            return

        if self.connection_results is None:
            job_conn_result = JobConnectionResult.objects.create()
            self.connection_results = job_conn_result
            self.save()
        if (
            self.inspection_results is None
            and self.scan_type == ScanTask.SCAN_TYPE_INSPECT
        ):
            job_inspect_result = JobInspectionResult.objects.create()
            self.inspection_results = job_inspect_result
            self.save()

        if self.tasks:
            # It appears the initialization didn't complete
            # so remove partial results
            self.tasks.all().delete()
            if self.connection_results is not None:
                self.connection_results.task_results.all().delete()
            if self.inspection_results is not None:
                self.inspection_results.task_results.all().delete()
            if self.details_report and self.details_report.deployment_report:
                self.details_report.deployment_report.system_fingerprints.delete()

        # Create tasks
        conn_tasks = self._create_connection_tasks()
        inspect_tasks = self._create_inspection_tasks(conn_tasks)
        self._create_fingerprint_task(conn_tasks, inspect_tasks)

        if self.scan_type != ScanTask.SCAN_TYPE_FINGERPRINT and (
            conn_tasks or inspect_tasks
        ):
            # this job runs an actual scan
            if self.scan:
                self.scan.most_recent_scanjob = self
                self.scan.save()

            for source in self.sources.all():
                source.most_recent_connect_scan = self
                source.save()

        self.status = target_status
        self.status_message = _(messages.SJ_STATUS_MSG_PENDING)
        self.save()
        self.log_current_status()

    def _create_connection_tasks(self):
        """Create initial connection tasks.

        :return: list of connection_tasks
        """
        conn_tasks = []
        if self.scan_type in [ScanTask.SCAN_TYPE_CONNECT, ScanTask.SCAN_TYPE_INSPECT]:
            count = 1
            for source in self.sources.all():
                # Create connect tasks
                conn_task = ScanTask.objects.create(
                    job=self,
                    source=source,
                    scan_type=ScanTask.SCAN_TYPE_CONNECT,
                    status=ScanTask.PENDING,
                    status_message=_(messages.ST_STATUS_MSG_PENDING),
                    sequence_number=count,
                )
                self.tasks.add(conn_task)
                conn_tasks.append(conn_task)

                # Create task result
                conn_task_result = TaskConnectionResult.objects.create(
                    job_connection_result=self.connection_results
                )

                # Add the task result to task
                conn_task.connection_result = conn_task_result
                conn_task.save()

                count += 1

        return conn_tasks

    def _create_inspection_tasks(self, conn_tasks):
        """Create initial inspection tasks.

        :param conn_tasks: list of connection tasks
        :return: list of inspection_tasks
        """
        inspect_tasks = []
        if conn_tasks and self.scan_type == ScanTask.SCAN_TYPE_INSPECT:
            count = len(conn_tasks) + 1
            for conn_task in conn_tasks:
                # Create inspect tasks
                inspect_task = ScanTask.objects.create(
                    job=self,
                    source=conn_task.source,
                    scan_type=ScanTask.SCAN_TYPE_INSPECT,
                    status=ScanTask.PENDING,
                    status_message=_(messages.ST_STATUS_MSG_PENDING),
                    sequence_number=count,
                )
                inspect_task.prerequisites.add(conn_task)
                self.tasks.add(inspect_task)
                inspect_tasks.append(conn_task)

                # Create task result
                inspect_task_result = TaskInspectionResult.objects.create(
                    job_inspection_result=self.inspection_results
                )

                # Add the inspect task result to task
                inspect_task.inspection_result = inspect_task_result
                inspect_task.save()

                count += 1
        return inspect_tasks

    def _create_fingerprint_task(self, conn_tasks, inspect_tasks):
        """Create initial inspection tasks.

        :param conn_tasks: list of connection tasks
        :param inspect_tasks: list of inspection tasks
        """
        if self.scan_type == ScanTask.SCAN_TYPE_FINGERPRINT or inspect_tasks:
            prerequisites = conn_tasks + inspect_tasks
            count = len(prerequisites) + 1
            # Create a single fingerprint task with dependencies
            fingerprint_task = ScanTask.objects.create(
                job=self,
                scan_type=ScanTask.SCAN_TYPE_FINGERPRINT,
                details_report=self.details_report,
                status=ScanTask.PENDING,
                status_message=_(messages.ST_STATUS_MSG_PENDING),
                sequence_number=count,
            )
            fingerprint_task.prerequisites.set(prerequisites)

            self.tasks.add(fingerprint_task)

    def status_start(self):
        """Change status from PENDING to RUNNING.

        :returns: bool True if successfully updated, else False
        """
        self.start_time = datetime.utcnow()
        target_status = ScanTask.RUNNING
        has_error = self.validate_status_change(target_status, [ScanTask.PENDING])
        if has_error:
            return False

        self.status = target_status
        self.status_message = _(messages.SJ_STATUS_MSG_RUNNING)
        self.save()
        self.log_current_status()
        return True

    def status_restart(self):
        """Change status from PENDING/PAUSED/RUNNING to PENDING.

        :returns: bool True if successfully updated, else False
        """
        target_status = ScanTask.PENDING
        has_error = self.validate_status_change(
            target_status, [ScanTask.PENDING, ScanTask.PAUSED, ScanTask.RUNNING]
        )
        if has_error:
            return False
        # Update tasks
        paused_tasks = self.tasks.filter(Q(status=ScanTask.PAUSED))
        if paused_tasks:
            for task in paused_tasks:
                task.status_restart()

        self.status = target_status
        self.status_message = _(messages.SJ_STATUS_MSG_RUNNING)
        self.save()
        self.log_current_status()
        return True

    @transaction.atomic
    def status_pause(self):
        """Change status from PENDING/RUNNING to PAUSED.

        :returns: bool True if successfully updated, else False
        """
        target_status = ScanTask.PAUSED
        has_error = self.validate_status_change(
            target_status, [ScanTask.PENDING, ScanTask.RUNNING]
        )
        if has_error:
            return False

        # Update tasks
        tasks_to_pause = self.tasks.exclude(
            Q(status=ScanTask.FAILED)
            | Q(status=ScanTask.CANCELED)
            | Q(status=ScanTask.COMPLETED)
        )
        if tasks_to_pause:
            for task in tasks_to_pause:
                task.status_pause()

        self.status = target_status
        self.status_message = _(messages.SJ_STATUS_MSG_PAUSED)
        self.save()
        self.log_current_status()
        return True

    @transaction.atomic
    def status_cancel(self):
        """Change status from CREATED/PENDING/RUNNING/PAUSED to CANCELED.

        :returns: bool True if successfully updated, else False
        """
        self.end_time = datetime.utcnow()
        target_status = ScanTask.CANCELED
        has_error = self.validate_status_change(
            target_status,
            [ScanTask.CREATED, ScanTask.PENDING, ScanTask.RUNNING, ScanTask.PAUSED],
        )
        if has_error:
            return False

        # Update tasks
        tasks_to_cancel = self.tasks.exclude(
            Q(status=ScanTask.FAILED)
            | Q(status=ScanTask.CANCELED)
            | Q(status=ScanTask.COMPLETED)
        )
        if tasks_to_cancel:
            for task in tasks_to_cancel:
                task.status_cancel()

        self.status = target_status
        self.status_message = _(messages.SJ_STATUS_MSG_CANCELED)
        self.save()
        self.log_current_status()
        return True

    def status_complete(self):
        """Change status from RUNNING to COMPLETE.

        :returns: bool True if successfully updated, else False
        """
        self.end_time = datetime.utcnow()
        target_status = ScanTask.COMPLETED
        has_error = self.validate_status_change(target_status, [ScanTask.RUNNING])
        if has_error:
            return False

        self.status = target_status
        self.status_message = _(messages.SJ_STATUS_MSG_COMPLETED)
        self.save()
        self._log_stats("COMPLETION STATS.")
        self.log_current_status()
        return True

    def status_fail(self, message):
        """Change status from RUNNING to FAILED.

        :param message: The error message associated with failure
        :returns: bool True if successfully updated, else False
        """
        self.end_time = datetime.utcnow()
        target_status = ScanTask.FAILED
        has_error = self.validate_status_change(target_status, [ScanTask.RUNNING])
        if has_error:
            return False

        self.status = target_status
        self.status_message = message
        self.log_message(self.status_message, log_level=logging.ERROR)
        self.save()
        self._log_stats("FAILURE STATS.")
        self.log_current_status(show_status_message=True, log_level=logging.ERROR)
        return True

    def validate_status_change(self, target_status, valid_current_status):
        """Validate and transition job status.

        :param target_status: Desired transition state
        :param valid_current_status: List of compatible current
        states for transition
        :returns bool indicating if it was successful:
        """
        if target_status == self.status:
            self.log_message(
                f"ScanJob status is already {target_status}", log_level=logging.DEBUG
            )
            return False

        if self.status not in valid_current_status:
            self.log_message(
                f"Cannot change job state to {target_status} when it is {self.status}",
                log_level=logging.ERROR,
            )
            return True
        return False
