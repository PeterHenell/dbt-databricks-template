"""Downloads the jars local Spark needs into PySpark's jars folder (run by local/Dockerfile).

- The Postgres JDBC driver, for the Hive metastore in the metastore-db service.
- Delta Lake, the table format Databricks uses. Each Delta release is built for one
  Spark version: 4.4.x is for Spark 4.2.
"""

import os
import urllib.request

import pyspark

MAVEN = "https://repo1.maven.org/maven2"
DELTA_VERSION = "4.4.0"
JARS = [
    f"{MAVEN}/org/postgresql/postgresql/42.7.4/postgresql-42.7.4.jar",
    f"{MAVEN}/io/delta/delta-spark_2.13/{DELTA_VERSION}/delta-spark_2.13-{DELTA_VERSION}.jar",
    f"{MAVEN}/io/delta/delta-storage/{DELTA_VERSION}/delta-storage-{DELTA_VERSION}.jar",
]

jars_dir = os.path.join(os.path.dirname(pyspark.__file__), "jars")
for url in JARS:
    target = os.path.join(jars_dir, url.rsplit("/", 1)[1])
    urllib.request.urlretrieve(url, target)
    print(f"Downloaded {url}")
