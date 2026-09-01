"""Shipment state lives on ``orders.Order``.

Logistics works order-by-order (no line level shipping), so this app carries
views and services rather than models of its own.
"""
