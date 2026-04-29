# ACLResourceSeed

`ACLResourceSeed` is the structured seed type used to define one resource node
for ACL bootstrap.

## Purpose

Some ACL systems require a known resource tree or resource catalog before
grants can be attached correctly.

This seed type lets that resource structure be declared in code.

## Typical Information

A resource seed usually represents:

- resource type
- resource key
- optional parent relationship
- optional descriptive fields

## When It Is Useful

- initial environment setup
- deterministic local/test data
- rebuilding known resource trees

## Related Types

- [ACLPermissionSeed](ACLPermissionSeed.md)
- [ACLGroupSeed](ACLGroupSeed.md)
- [ACLBootstrapper](ACLBootstrapper.md)
