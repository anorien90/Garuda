#!/bin/bash

# This script is used to purge all data from the database. It will drop all tables and recreate them.
sudo rm -rf ./data/qdrant/collections/pages/* | echo "No Qdrant data to remove"
sudo rm -rf ./data/garuda/crawler.db | echo "No Garuda crawler database to remove"
