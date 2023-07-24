from asgi_proxy import asgi_proxy
import base64
import click
import json
import os
import uvicorn


class CustomEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, bytes):
            return {"$base64": base64.b64encode(obj).decode()}
        return super().default(obj)


def as_base64(dct):
    if '$base64' in dct:
        return base64.b64decode(dct["$base64"])
    return dct


@click.group()
def asgi_replay():
    pass


@asgi_replay.command()
@click.argument("url")
@click.argument(
    "filename", type=click.Path(file_okay=True, writable=True, allow_dash=True)
)
@click.option("--increment", is_flag=True, default=False)
@click.option("--host", default="127.0.0.1")
@click.option("--port", default=8000, type=int)
def record(url, filename, increment, host, port):
    i = 0

    proxy_app = asgi_proxy(url)

    async def app(scope, receive, send):
        nonlocal i
        # Each call to this writes to a file
        if increment:
            base, ext = os.path.splitext(filename)
            temp_filename = f"{base}-{i}{ext}"
        else:
            temp_filename = filename

        fp = open(temp_filename, "w")
        _send = send

        async def send(packet):
            fp.write(json.dumps(packet, cls=CustomEncoder) + "\n")
            await _send(packet)

        await proxy_app(scope, receive, send)

        fp.close()
        print(scope["method"], scope["path"], "written to", temp_filename)
        i += 1

    uvicorn.run(app, host=host, port=port)

@asgi_replay.command()
@click.argument("filename")
@click.option("--host", default="127.0.0.1")
@click.option("--port", default=8000, type=int)
def replay(filename, host, port):
    # An ASGI server that replays the exact request for every incoming hit
    lines = []
    with open(filename) as fp:
        for line in fp.readlines():
            if line.strip():
                lines.append(json.loads(line, object_hook=as_base64))

    async def app(scope, receive, send):
        if scope["type"] != "http":
            return
        for line in lines:
            await send(line)

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    asgi_replay()
