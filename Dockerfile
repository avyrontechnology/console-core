FROM python:3.11.8-slim

ENV PYTHONUNBUFFERED 1

EXPOSE 8001 50051
WORKDIR /console-service

COPY poetry.lock pyproject.toml ./

RUN pip3 install poetry==1.8.2
RUN poetry config virtualenvs.create false

# Regenerate the lock file to sync with pyproject.toml
RUN poetry lock --no-update

RUN poetry install

COPY . ./

# Command to start both FastAPI and gRPC servers
# CMD (poetry run uvicorn --host=0.0.0.0 --port=8001 src.main:app --reload & \
#     python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. your_grpc_service.proto && \
#     python your_grpc_service.py)


# Command to start both FastAPI and gRPC servers
CMD (poetry run uvicorn --host=0.0.0.0 --port=8001 src.main:app --reload & \
    python -m src.rpc_main)
