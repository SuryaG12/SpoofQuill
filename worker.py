"""Cloudflare Worker entry point for SpoofQuill."""

from workers import WorkerEntrypoint

from backend.app import app


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        import asgi

        return await asgi.fetch(app, request.js_object, self.env)
