#!/usr/bin/env python
"""
Banger - X/Twitter Post Generator

Main entry point for running the application.

Usage:
    Server mode (default):
        python run.py
        
    CLI mode (generate posts interactively):
        python run.py --cli
        
    Run tweet scraper:
        python run.py --scrape
"""

import sys
import argparse


def run_server(port: int = 8000):
    """Start the FastAPI server."""
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        reload=True,
    )


def run_cli():
    """Run interactive CLI for post generation."""
    from app.core.generator import (
        pick_mode_for_today,
        get_daily_context,
        build_prompt,
        generate_multiple_options,
    )
    
    mode = pick_mode_for_today()
    print(f"\n🎯 Mode: {mode}")
    
    daily_context = get_daily_context()
    prompt = build_prompt(mode, daily_context)
    options = generate_multiple_options(prompt, mode)

    print("\n=== Generated Options ===\n")
    for i, option in enumerate(options, 1):
        print(f"{i}. {option}\n")


def run_scraper():
    """Run the tweet scraper to update style profile."""
    from scripts.tweet_scraper import main as scraper_main
    scraper_main()


def main():
    parser = argparse.ArgumentParser(
        description="Banger - X/Twitter Post Generator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--cli",
        action="store_true",
        help="Run in CLI mode for interactive post generation",
    )
    parser.add_argument(
        "--scrape",
        action="store_true", 
        help="Run tweet scraper to update style profile",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to run the server on (default: 8000)",
    )
    
    args = parser.parse_args()
    
    if args.cli:
        run_cli()
    elif args.scrape:
        run_scraper()
    else:
        run_server(args.port)


if __name__ == "__main__":
    main()
