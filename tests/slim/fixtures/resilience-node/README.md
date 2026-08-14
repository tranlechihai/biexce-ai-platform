# Resilience Node fixture

Dependency-free Node.js project used as the second Step 3 acceptance project.
The baseline is green before a new requirement changes an existing expectation.

Validation:

```text
npm test
```

No network, package installation, database, or production action is required.
The script uses Node's in-process test isolation so validation does not depend
on permission to spawn test workers.
