# Copyright (c) 2018-2019 Red Hat, Inc.
#
# This software is licensed to you under the GNU General Public License,
# version 3 (GPLv3). There is NO WARRANTY for this software, express or
# implied, including the implied warranties of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. You should have received a copy of GPLv3
# along with this software; if not, see
# https://www.gnu.org/licenses/gpl-3.0.txt.

"""Initial processing of the shell output from the cpu role."""

import logging

from api.common.util import convert_to_int, is_int

from scanner.network.processing import process
from scanner.network.processing.util import get_line

logger = logging.getLogger(__name__)  # pylint: disable=invalid-name

# pylint: disable=too-few-public-methods

# #### Processors ####


class ProcessCpuModelVer(process.Processor):
    """Process the model version of the cpu."""

    KEY = 'cpu_model_ver'

    @staticmethod
    def process(output, dependencies=None):
        """Pass the output back through."""
        return get_line(output['stdout_lines'])


class ProcessCpuCpuFamily(process.Processor):
    """Process the cpu family."""

    KEY = 'cpu_cpu_family'

    @staticmethod
    def process(output, dependencies=None):
        """Pass the output back through."""
        return get_line(output['stdout_lines'])


class ProcessCpuVendorId(process.Processor):
    """Process the vendor id of the cpu."""

    KEY = 'cpu_vendor_id'

    @staticmethod
    def process(output, dependencies=None):
        """Pass the output back through."""
        return get_line(output['stdout_lines'])


class ProcessCpuModelName(process.Processor):
    """Process the model name of the cpu."""

    KEY = 'cpu_model_name'

    @staticmethod
    def process(output, dependencies=None):
        """Pass the output back through."""
        return get_line(output['stdout_lines'])


class ProcessCpuBogomips(process.Processor):
    """Process the bogomips of the cpu."""

    KEY = 'cpu_bogomips'

    @staticmethod
    def process(output, dependencies=None):
        """Pass the output back through."""
        return get_line(output['stdout_lines'])


class ProcessCpuSocketCount(process.Processor):
    """Process the cpu socket count."""

    KEY = 'cpu_socket_count'
    DEPS = ['internal_cpu_socket_count_dmi_cmd',
            'internal_cpu_socket_count_cpuinfo_cmd',
            'cpu_count']
    REQUIRE_DEPS = False

    @staticmethod
    def process(output, dependencies):
        """Return the correct value for cpu_socket_count output."""
        # process the internal dmi cpu socket count result
        dmi_cpu_socket_count = \
            dependencies.get('internal_cpu_socket_count_dmi_cmd')
        if dmi_cpu_socket_count and dmi_cpu_socket_count.get('rc') == 0:
            dmi_count = dmi_cpu_socket_count.get('stdout').strip()
            if is_int(dmi_count):
                if convert_to_int(dmi_count) != 0 and \
                        convert_to_int(dmi_count) <= 8:
                    return convert_to_int(dmi_count)

        # process the cpuinfo socket count as a fallback
        cpuinfo_cpu_socket_count = \
            dependencies.get('internal_cpu_socket_count_cpuinfo_cmd')
        if cpuinfo_cpu_socket_count and \
                cpuinfo_cpu_socket_count.get('rc') == 0 and \
                cpuinfo_cpu_socket_count.get('stdout_lines'):
            cpuinfo_count = cpuinfo_cpu_socket_count.get(
                'stdout_lines', [0])[0]
            if is_int(cpuinfo_count):
                if convert_to_int(cpuinfo_count) != 0 and \
                        convert_to_int(cpuinfo_count) <= 8:
                    return convert_to_int(cpuinfo_count)

        # assign the socket_count to the cpu_count as a last resort
        cpu_count = dependencies.get('cpu_count')
        if is_int(cpu_count):
            return convert_to_int(cpu_count)
        return None


class ProcessCpuCoreCount(process.Processor):
    """Process the cpu core count."""

    KEY = 'cpu_core_count'
    DEPS = ['cpu_socket_count',
            'cpu_core_per_socket',
            'cpu_count',
            'cpu_hyperthreading',
            'virt_type']
    REQUIRE_DEPS = False

    @staticmethod
    def process(output, dependencies):
        """Return the correct value for cpu core count output."""
        cpu_socket_count = dependencies.get('cpu_socket_count')
        cpu_core_per_socket = dependencies.get('cpu_core_per_socket')
        cpu_count = dependencies.get('cpu_count')
        cpu_hyperthreading = dependencies.get('cpu_hyperthreading')
        virt_type = dependencies.get('virt_type')
        # if the virt_type is vmware and cpu_count exists
        # then return cpu_count
        if virt_type and virt_type == 'vmware' and is_int(cpu_count):
            return convert_to_int(cpu_count)
        # if the cpu_core_per_socket & the cpu_socket_count are present
        # return the product of the two
        if is_int(cpu_core_per_socket) and is_int(cpu_socket_count):
            return convert_to_int(cpu_core_per_socket) * \
                convert_to_int(cpu_socket_count)
        if is_int(cpu_count):
            if cpu_hyperthreading:
                return convert_to_int(cpu_count) / 2
            # if there is no threading, return the cpu count
            return convert_to_int(cpu_count)
        return None
