"""gRPC server bootstrap for Anki integration."""

from __future__ import annotations

import asyncio

import grpc

from grpc_svc.pb.tutor.v1 import tutor_pb2_grpc
from grpc_svc.servicer import TutorGrpcServicer
from langgraph.graph.state import CompiledStateGraph
from logger import startup_logger


async def serve_grpc(graph: CompiledStateGraph, host: str, port: int) -> grpc.aio.Server:
    address = f"{host}:{port}"
    server = grpc.aio.server()
    tutor_pb2_grpc.add_TutorServiceServicer_to_server(TutorGrpcServicer(graph, address), server)
    server.add_insecure_port(address)
    await server.start()
    startup_logger.info(f"grpc.start addr={address}")
    return server


async def run_grpc_server(graph: CompiledStateGraph, host: str, port: int) -> None:
    server = await serve_grpc(graph, host, port)
    try:
        await server.wait_for_termination()
    except asyncio.CancelledError:
        await server.stop(grace=5)
        raise
