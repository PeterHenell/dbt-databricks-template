# dbt on Databricks template

A repository template that gives a data engineering team one dbt project per data product, isolated personal development environments, and a deployment pattern to Databricks.

## Platform

**Dev workspace**:
The Databricks workspace where all development happens; it can read prod catalogs but never writes to them.
_Avoid_: sandbox, development cluster

**Prod workspace**:
The Databricks workspace where deployed data products are built and served.

**Team catalog**:
The Unity Catalog catalog in the dev workspace owned by one team, shared by all of that team's data products and developers.
_Avoid_: dev catalog, sandbox catalog

**Product catalog**:
A Unity Catalog catalog that holds exactly one data product in one environment. Each data product has a **product dev catalog** (in the dev workspace) and a **product prod catalog** (in the prod workspace).
_Avoid_: product catalog without "dev" or "prod" when the environment matters

**Release**:
A GitLab release that bundles one or more merged changes and, after manual approval, is deployed to the product prod catalog.
_Avoid_: deploy (for the bundle of changes)

**Data product version**:
The version of a released, deployed package of the data product; every release is a new data product version, whether or not the published interface changed.
_Avoid_: contract version (that versions the interface)

## Data product

**Data product**:
A dataset with consumers that is built by one dbt project in one repository and deployed into its own product catalog.
_Avoid_: project (when the dataset is meant), domain

**Layer**:
One stage of the project's model graph, stored in its own schema: `staging`, `intermediate`, or a published version.
_Avoid_: zone, tier, medallion level

**Published interface**:
The models in a data product that consumers may read; everything outside the published interface is internal.
_Avoid_: marts, output port, public layer

**Contract version**:
A version of the data contract; its major number (`v1`, `v2`, …) names the schema the published interface is stored in. How contract versions are managed is an open question.
_Avoid_: product version, model version (when the whole interface is meant)

**Data contract**:
The ODCS document describing one major contract version, generated from the dbt project.
_Avoid_: schema contract, interface spec

**Breaking change**:
A change to the published interface that can break an existing consumer of the same major contract version.

## Development

**Developer alias**:
A short name for one developer, used in their schema names (default: first two letters of first and last name, e.g. `pehe`).
_Avoid_: username, handle

**Personal environment**:
The set of schemas in the team catalog prefixed `<product>__<alias>__`, owned by one developer for one data product.
_Avoid_: sandbox, dev schema (singular)

**Source mode**:
Where a personal environment reads its sources from: `prod` (directly), `clone` (personal shallow clones) or `sample` (personal small samples).

**Deferred build**:
A dev build of only the changed models, with references to unchanged models resolved against the prod deployment.
_Avoid_: slim build, partial build
