import argparse

from agents.registry import agent_names, build_agent


def parse_args():
    parser = argparse.ArgumentParser(description="Run one data team agent.")
    parser.add_argument("agent", choices=agent_names())
    return parser.parse_args()


def main():
    args = parse_args()
    build_agent(args.agent).run()


if __name__ == "__main__":
    main()
