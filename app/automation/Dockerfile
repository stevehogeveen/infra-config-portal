FROM python:3.12.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends openssh-client && rm -rf /var/lib/apt/lists/*
COPY app/backend/requirements.txt /workspace/app/backend/requirements.txt
COPY app/automation/requirements.txt /workspace/app/automation/requirements.txt
RUN pip install --no-cache-dir -r /workspace/app/automation/requirements.txt
COPY app/automation/collections.yml /tmp/collections.yml
RUN ansible-galaxy collection install -r /tmp/collections.yml -p /usr/share/ansible/collections
ENV ANSIBLE_COLLECTIONS_PATH=/usr/share/ansible/collections ANSIBLE_HOME=/tmp/ansible
COPY app/backend/app /workspace/app/backend/app
COPY app/automation /workspace/app/automation
RUN useradd --uid 10001 --create-home automation
WORKDIR /workspace/app/backend
USER automation
CMD ["rq", "worker", "--serializer", "rq.serializers.JSONSerializer", "inventory"]
