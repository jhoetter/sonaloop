# sonaloop-mcp

The one-sentence install shim for the [Sonaloop](https://github.com/jhoetter/sonaloop-research) MCP
server. It exists so the documented one-liner works verbatim with nothing but `uv` installed:

```bash
claude mcp add sonaloop -- uvx sonaloop-mcp
```

(uvx resolves the command name as a PyPI package name, so `uvx sonaloop-mcp` needs this
distribution; the actual server lives in the [`sonaloop`](https://pypi.org/project/sonaloop/)
package this depends on.)

Docs: <https://jhoetter.github.io/sonaloop-docs/getting-started/>
