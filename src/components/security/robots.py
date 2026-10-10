import os

from fastapi import APIRouter, Response


class RobotsController:

    robot_router = APIRouter()

    @robot_router.get("/robots.txt")
    async def read_robots():
        robots_path = os.path.join(os.path.dirname(__file__), "robots.txt")
        with open(robots_path, "r") as file:
            content = file.read()
        return Response(content=content, media_type="text/plain")
