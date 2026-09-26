"""Isolated model workers.

Heavy GPU models may run in short-lived subprocesses so their CUDA context and
model dependencies die with the worker instead of accumulating in the FastAPI
backend process.
"""
