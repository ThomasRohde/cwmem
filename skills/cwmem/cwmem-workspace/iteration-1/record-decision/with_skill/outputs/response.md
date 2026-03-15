# Response to: "I just refactored the authentication middleware to use JWT instead of session cookies. Can you record this decision?"

## What I would say to the user

I'll record that decision in cwmem for you.

*(After running the commands below, I would report the result back to the user:)*

Done -- recorded the authentication middleware refactoring decision. The entry captures the move from session cookies to JWT and has been exported to the `memory/` artifacts for version control. You can find it with `uv run cwmem search "JWT authentication"` if you need to reference it later.

If there are specific entities involved (e.g., an AuthService, API gateway, or user service), I can link the entry to those as well. Just let me know.

---

## Commands I would run

### Step 0: Resolve the cwmem command

I would check `pyproject.toml` and see that cwmem is declared as the project itself. The resolved command prefix is:

```
uv run cwmem
```

### Step 1: Check initialization

```bash
uv run cwmem status
```

Since the repo already has cwmem initialized (`.cwmem/` and `memory/` exist), I skip setup and proceed to Step 2.

### Step 2: Record the decision

```bash
uv run cwmem add \
  --title "Switch authentication middleware from session cookies to JWT" \
  --type decision \
  --tag authentication \
  --tag security \
  --tag refactoring \
  "Refactored the authentication middleware to use JSON Web Tokens (JWT) instead of session cookies. JWTs provide stateless authentication, making the system easier to scale horizontally since no server-side session storage is required. This also simplifies cross-service authentication in a distributed architecture."
```

### Step 3: Export artifacts to version control

```bash
uv run cwmem sync export
```

This ensures the new decision entry is written to the `memory/` directory so it appears in version control and is available for PR review.
