# One artifact per release, deployed unchanged to product dev and prod

The release pipeline builds one archive: the bundle, the dbt project, the installed `dbt_packages/` and `deploy/profiles.yml`. It's stored once in GitLab's generic package registry as package `<product>`, version `<release tag>`. The same archive is deployed to product dev, tested by a job run there, and then deployed to prod. Nothing is rebuilt from source in between, so prod gets exactly what passed in product dev. That works only because the archive holds no environment-specific values: catalogs, hosts, warehouses and identities come from bundle targets and CI variables when deploying. We rejected building an artifact for every `main` commit, because only releases are ever deployed.

## Consequences

- An artifact is written once. Re-running a release pipeline reuses it; changing a release needs a new tag.
- Release tags must be valid GitLab package version names.
