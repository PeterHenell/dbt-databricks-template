# All MR builds share one set of schemas and run one at a time

MR pipelines build the whole project into one fixed, permanent set of schemas, `<product>__mr__<layer>`, in the team catalog. They don't get a schema set per MR. Builds share a GitLab `resource_group` so only one runs at a time, and each starts by dropping those schemas, so tables left over from another branch can't hide a missing model. Teams are small, so waiting in the queue is cheaper than creating and cleaning up schemas per MR via GitLab environments and stop actions.

## Consequences

- MR builds are full builds without `--defer` in the first version. Deferring against product dev is the planned way to reduce rebuild costs later.
