# Security policy

## Reporting

Please **do not** open a public issue for a vulnerability. Report it privately
to the maintainer (see the commit author / GitHub profile) with:

- affected version (commit hash),
- a minimal reproduction,
- impact assessment.

You can expect an acknowledgement within a few days.

## Scope

`blender-loop` starts subprocesses (Blender, or any binary you point it at) and
writes files under the work directory it is given. Relevant risks:

- **Command construction**: paths and arguments are passed as a list (never a
  shell string), so parameter values cannot become shell metacharacters.
- **Resource exhaustion**: `memory_mb` and `timeout_s` exist to bound child
  processes; treat untrusted inputs as potentially expensive.
- **File writes**: evaluators receive `workdir`; they should not write outside
  it. The library itself only writes the paths you pass to it.

## Not a sandbox

This is not a security sandbox. Do not evaluate untrusted Blender scripts with
it; run those in a container/VM with their own limits.
