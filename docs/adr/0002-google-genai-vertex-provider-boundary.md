# ADR 0002: Google Gen AI Vertex Provider Boundary

## Status

Accepted.

## Decision

The backend uses `google-genai` as the single SDK for Gemini, Imagen, and Veo.
Vertex access is isolated behind `genai.Client(vertexai=True, ...)` in the
provider service boundary.

## Rationale

A single SDK and a narrow client boundary reduce credential, dependency, and
testing complexity. Mock mode can replace provider behavior without changing API
routes, job handlers, storage, or frontend code.

## Consequences

Benefits:

- one credential model for prompt, image, and video providers
- consistent public error mapping
- deterministic tests with fake clients
- easier readiness reporting

Trade-offs:

- live provider behavior still needs manual QA
- SDK surface changes can affect several media flows
- credential handling must remain carefully isolated

## Follow-Up

Keep provider tests focused on inline bytes parsing, base64 decoding, safety
mapping, public errors, and credential readiness.
