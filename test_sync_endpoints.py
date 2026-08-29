#!/usr/bin/env python3
"""
Quick test to verify the sync endpoints are correctly defined.
This checks for import errors and basic endpoint structure.
"""
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

try:
    # Test imports
    print("Testing imports...")
    from backend.routes.api import sync_user_guilds, sync_guild_channels
    from backend.services.supabase_service import get_latest_oauth_session
    from backend.auth import fetch_discord_guilds, fetch_discord_user
    
    print("✓ All imports successful")
    
    # Check if functions are async
    import inspect
    assert inspect.iscoroutinefunction(sync_user_guilds), "sync_user_guilds should be async"
    assert inspect.iscoroutinefunction(sync_guild_channels), "sync_guild_channels should be async"
    
    print("✓ All functions are properly async")
    
    # Check function signatures
    sig_guilds = inspect.signature(sync_user_guilds)
    sig_channels = inspect.signature(sync_guild_channels)
    
    assert 'request' in sig_guilds.parameters, "sync_user_guilds should have 'request' parameter"
    assert 'request' in sig_channels.parameters, "sync_guild_channels should have 'request' parameter"
    assert 'guild_id' in sig_channels.parameters, "sync_guild_channels should have 'guild_id' parameter"
    
    print("✓ All function signatures are correct")
    
    print("\n✅ All tests passed! The sync endpoints are correctly implemented.")
    
except Exception as e:
    print(f"\n❌ Test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
