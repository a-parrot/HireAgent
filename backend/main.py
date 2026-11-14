import uvicorn

from app.core.config import Settings


def main():
    settings = Settings()
    uvicorn.run("app.main:app", host=settings.app_host, port=settings.app_port)


if __name__ == "__main__":
    main()
