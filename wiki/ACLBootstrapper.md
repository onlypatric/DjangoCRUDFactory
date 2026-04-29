# ACLBootstrapper

`ACLBootstrapper` is the helper used to seed and maintain initial ACL data.

## Purpose

It exists so projects can define their starting ACL data in a structured way
instead of manually inserting rows every time.

Typical seeded data includes:

- permissions
- groups
- resources
- memberships
- grants

## Typical Use Cases

- first project setup
- repeatable local development seeding
- test environment bootstrap
- controlled initialization of ACL catalogs

## Seed Types It Works With

- [ACLPermissionSeed](ACLPermissionSeed.md)
- [ACLGroupSeed](ACLGroupSeed.md)
- [ACLResourceSeed](ACLResourceSeed.md)

## Relationship To Management Commands

The management commands provided by the library are wrappers around this
bootstrap functionality.
