# GitHub security preflight

GitHub's built-in Actions token does not normally expose administration-read
branch-protection endpoints. The publisher therefore accepts a separate
`THUHA_GITHUB_SECURITY_TOKEN`, scoped only to this repository with the read
permissions needed to inspect main/factory-state protection and the protected
environment. It is used only for GET security checks; the state adapter retains
its separate contents-write token. A missing or insufficient security reader
blocks publication rather than turning an unknown control into PASS.

Store a newly authorized credential in the protected thuha-production
environment only during the separately approved go-live setup. Do not paste it
in chat, commit it, or copy a secret from another repository. No security token
has been created or configured by this implementation. Credentials-presence
checks print booleans only. No API changes repository security settings.
