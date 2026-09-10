# ADR 0006 — GHCR image tags for FTS core and UI (verified August 2026)

- **Estado:** Aceptado (2026-08)
- **Contexto:** The originally drafted compose used digest placeholders (`@sha256:DIGEST_CORE` / `@sha256:DIGEST_UI`) assuming tags `2.2.1` existed. User's server-side digest resolution (`docker buildx imagetools inspect ghcr.io/freetakteam/freetakserver:2.2.1`) failed with "not found" for both core and UI images.
- **Verification:** GitHub Packages container registry pages confirm:
  - `ghcr.io/freetakteam/freetakserver` has NO tag `2.2.1`. Tagged versions are commit-SHA tags plus `v2_2_1` (FTS 2.2.1 build, digest `sha256:cc6147ba031c03406ff63abe35641cd2f9efb6f507b88617a1c099e0ff87a866`), `_v2_2_1` (latest alias), `master`, and `_2_2`.
  - `ghcr.io/freetakteam/ui` likewise has no `2.2.1` tag; current release line is `master` (digest `sha256:eeaf23ef435068ac90f05a18fbad58db6d350fdc204b4bae4f6f98a42a51b004`) plus older commit-SHA tags.
- **Decisión:** Compose uses `ghcr.io/freetakteam/freetakserver:v2_2_1` (core, FTS 2.2.1) and `ghcr.io/freetakteam/ui:master` (UI). After first successful pull, pin by digest per ADR 0005.
- **Consecuencias:** Deployment works immediately; digest pinning remains a follow-up hardening step. `master` tag for UI is mutable and should be digest-pinned after first pull.
- **Alternativas descartadas:** pinning to non-existent `2.2.1` tags (breaks deploy); building from source (ADR 0001 plan B only).

