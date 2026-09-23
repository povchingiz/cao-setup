# Code Taste & Simplicity Guidelines

1. **Minimal Abstractions**: Avoid premature generalization, excessive design patterns, factory classes, and unnecessary indirection. If a function is called once, keep it inline or flat.
2. **Standard Library First**: Do not pull external dependencies for tasks solved by standard tools (e.g. `math`, `json`, `pathlib`, `subprocess`).
3. **Single Responsibility & Pure Functions**: Prefer pure, deterministic functions without hidden side effects.
4. **Localized Changes**: No drive-by refactoring. Edit strictly what the current task requires.
5. **Explicit Over Implicit**: Code should read like plain documentation. Avoid meta-programming and magic decorators unless standard for the framework.
