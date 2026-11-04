# dbt + Apache Spark (PySpark, Delta Lake) for running the project locally.
# Build context: local/ (see local/compose.yml).
FROM docker.io/library/python:3.12-slim
# Spark runs on the JVM; dbt uses git for `dbt deps`.
RUN apt-get update \
    && apt-get install -y --no-install-recommends openjdk-21-jre-headless procps git \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY install-jars.py /tmp/install-jars.py
RUN python /tmp/install-jars.py
COPY spark/ /opt/spark-conf/
ENV SPARK_CONF_DIR=/opt/spark-conf
WORKDIR /project
ENTRYPOINT ["dbt"]
CMD ["build"]
