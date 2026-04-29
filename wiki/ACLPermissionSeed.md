# ACLPermissionSeed

`ACLPermissionSeed` is the structured seed type used to define one permission
entry for ACL bootstrap.

## Purpose

It lets you define permissions in Python code instead of manually creating them
in the database.

## Typical Information

A permission seed commonly carries data such as:

- permission key
- human-readable label or description
- optional categorization fields depending on the implementation

## Example Use

You define a list of permission seeds and pass them to the bootstrap flow so
the permission catalog can be created or synchronized.

## Related Seed Types

- [ACLGroupSeed](ACLGroupSeed.md)
- [ACLResourceSeed](ACLResourceSeed.md)
- [ACLBootstrapper](ACLBootstrapper.md)
