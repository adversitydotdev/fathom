from ogrl_integration import Integration

app = Integration("dev.ogrl.aws", "0.1.0")


@app.validate
def validate(ctx):
    return ctx.identity("test account")


@app.resource("account", version=1)
def account(ctx):
    yield {"id": "123456789012", "name": "test"}
