import sys
import subprocess

def main():
    if len(sys.argv) == 1:
        print("Usage: garuda-docker [up|down|ps|logs|exec ...]\n"
              "Runs common docker-compose commands for Garuda.")
        sys.exit(1)
    command = sys.argv[1:]
    full_cmd = ["docker-compose"] + command
    print(f"Running: {' '.join(full_cmd)}")
    subprocess.run(full_cmd)

if __name__ == "__main__":
    main()

