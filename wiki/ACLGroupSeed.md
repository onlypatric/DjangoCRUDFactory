# ACLGroupSeed

`ACLGroupSeed` is the structured seed type used to define one ACL group during
bootstrap.

## Purpose

It lets the project declare initial group data in code.

Examples:

- administrators
- operators
- readers
- tenant-specific support roles

## Typical Information

A group seed usually contains:

- group code or slug
- group name
- optional description

## When It Is Used

During ACL bootstrap and repeatable environment setup.

## Related Types

- [ACLPermissionSeed](ACLPermissionSeed.md)
- [ACLResourceSeed](ACLResourceSeed.md)
- [ACLBootstrapper](ACLBootstrapper.md)
