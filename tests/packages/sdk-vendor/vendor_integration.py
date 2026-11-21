"""An SDK integration whose query sources run against the test emulator."""

from ogrl_integration import Integration

app = Integration("dev.ogrl.vendor", "0.1.0")


@app.validate
def validate(ctx):
    return ctx.identity(f"emulator on {ctx.config['port']}")


@app.resource("status", version=1)
def status(ctx):
    yield {"id": "up", "name": "up"}
