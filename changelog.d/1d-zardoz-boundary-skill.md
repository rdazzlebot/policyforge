**The shell answers "what does this send anywhere?"** `boundary` is the
eleventh zardoz skill: what may be sent to the configured model, which
provider it goes to, and which content classes are allowed to reach it.

```
> what does this send to a model?

Answering for this shell's configuration: openai-compat, model qwen3:14b,
via http://localhost:11434/v1.
Classified as: local (inferred: localhost is this machine)

content                local        self-hosted  third-party
public-domain          yes          yes          yes
organization-internal  yes          yes          yes
licensed               yes          no           no

No ceiling is tightened by config; these are the defaults.
```

**It answers for the provider the shell is actually configured with**, and
says which one that is before it shows anything else. A user asking this
question is sitting inside a model interface at the time — an answer about
some other provider would be worse than no answer, because it is
confidently about the wrong thing. The same reason a citation count means
nothing without the catalogs it was taken over.

`policyforge boundary` on the command line is unchanged and still takes
`--path` to classify files.
