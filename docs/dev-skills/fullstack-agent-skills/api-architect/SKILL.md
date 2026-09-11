---
name: api-architect
description: Design REST API architecture for an application. Use when defining resources, endpoints, request and response contracts, validation, business logic boundaries, authentication, errors, pagination, filtering, and frontend API requirements before backend implementation.
---

# API Architect

Design a complete, minimal REST API that supports the application workflows.

## Responsibilities

1. Understand domain entities, user workflows, frontend needs, and authorization boundaries.
2. Model resources around domain concepts rather than individual UI components.
3. Define all required endpoints with method, path, purpose, request, response, and important status codes.
4. Keep URLs resource-oriented and use HTTP methods consistently.
5. Define validation rules and business rules separately.
6. Define authentication and authorization requirements per endpoint.
7. Define consistent error responses.
8. Add pagination, filtering, sorting, and search only where required.
9. Identify operations requiring transactions, idempotency, concurrency handling, or asynchronous processing.
10. Avoid duplicate endpoints and unnecessary generic CRUD when the application does not need it.
11. Ensure every frontend workflow is supported end to end.

## Output

Produce:

- resource model
- endpoint table
- request/response contracts
- validation/business rules
- authentication/authorization rules
- error model
- important persistence/transaction considerations
- frontend-to-endpoint mapping

Do not implement the backend unless explicitly requested.
