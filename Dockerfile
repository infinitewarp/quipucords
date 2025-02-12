FROM redhat/ubi9-minimal

ENV DJANGO_DB_PATH=/var/data/
ENV DJANGO_DEBUG=False
ENV DJANGO_LOG_FILE=/var/log/app.log
ENV DJANGO_LOG_FORMATTER=verbose
ENV DJANGO_LOG_HANDLERS=console,file
ENV DJANGO_LOG_LEVEL=INFO
ENV DJANGO_SECRET_PATH=/var/data/secret.txt
ENV LANG=C
ENV LC_ALL=C
ENV PATH="/opt/venv/bin:${PATH}"
ENV PRODUCTION=True
ENV PYTHONPATH=/app/quipucords
ENV QUIPUCORDS_LOG_LEVEL=INFO

COPY scripts/dnf /usr/local/bin/dnf
ARG BUILD_PACKAGES="crypto-policies-scripts gcc postgresql-devel python3.11-devel"
RUN dnf install \
        git \
        glibc-langpack-en \
        jq \
        make \
        openssh-clients \
        procps-ng \
        python3.11 \
        python3.11-pip \
        sshpass \
        tar \
        which \
        ${BUILD_PACKAGES} \
        -y &&\
    dnf clean all &&\
    python3.11 -m venv /opt/venv

# set cryptographic policy to a mode compatible with older systems (like RHEL5&6)
RUN update-crypto-policies --set LEGACY

RUN pip install --upgrade pip wheel

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
RUN dnf remove ${BUILD_PACKAGES} -y && \
    dnf clean all

# Fetch UI code
COPY Makefile .
ARG UI_RELEASE="latest"
RUN make fetch-ui -e QUIPUCORDS_UI_RELEASE=${UI_RELEASE}

# Create /etc/ssl/qpc
COPY deploy/ssl /etc/ssl/qpc

# Create /deploy
COPY deploy  /deploy

# Create log directories
VOLUME /var/log

# Create /var/data
RUN mkdir -p /var/data
VOLUME /var/data

# Copy server code
COPY . .

# Install quipucords as package
RUN pip install -v -e .

# Collect static files
RUN make server-static

# Allow git to run in /app
RUN git config --file /.gitconfig --add safe.directory /app

EXPOSE 8000
CMD ["/bin/bash", "/deploy/entrypoint_web.sh"]
