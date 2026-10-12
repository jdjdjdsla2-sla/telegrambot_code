#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gateway 플러그인 어댑터
Hermes Gateway pre_gateway_dispatch 훅 등록

플러그인 규약:
- __init__.py에 register(ctx) 함수 정의
- ctx.register_hook(hook_name, callback)으로 등록
"""

import logging

logger = logging.getLogger(__name__)


def register(ctx) -> None:
    """
    Gateway 플러그인 등록 함수 (규약: register(ctx)).

    Args:
        ctx: PluginContext (hermes_cli.plugins.PluginContext)
    """
    from .router import pre_gateway_dispatch_handler
    ctx.register_hook("pre_gateway_dispatch", pre_gateway_dispatch_handler)
    logger.info("remote_dev: pre_gateway_dispatch 훅 등록 완료")


def unregister(ctx) -> None:
    """플러그인 제거 (테스트용)."""
    try:
        from .router import pre_gateway_dispatch_handler
        ctx.unregister_hook("pre_gateway_dispatch", pre_gateway_dispatch_handler)
        logger.info("remote_dev: pre_gateway_dispatch 훅 제거 완료")
    except Exception as e:
        logger.warning("remote_dev: hook unregistration failed: %s", e)
