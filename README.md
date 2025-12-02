# Prime Genius Math Game

## Description
Math Genius game is a multiplayer game where a grid of numbers is presented to players. The goal is for a player to select as many correct PRIME numbers as possible within a time limit. The player with the most correct selections wins the game. An incorrect selection results -3 to that player's score. A correct prime number selection results in +2 to that player's score.

## How to play

1. Run the server by executing `server.py --server_ip <IP_ADDRESS> --server_port <PORT>`
2. Run an instance of the client by executing `client.py --server_ip <IP_ADDRESS> --server_port <PORT>` for **each player that wants to play**
3. Each player needs to select their name and click READY-UP
4. Once all players are ready, the server will start the game

EXAMPLE:
- Start server: `python server.py --server_ip 192.168.1.5 --server_port 5555`
- Client 1: `python client.py --server_ip 192.168.1.5 --server_port 5555`
- Client 2: `python client.py --server_ip 192.168.1.5 --server_port 5555`

## Important NOTES for Running the Game
- Easiest way to play the game, is to run the server and all the clients on the same device (localhost). To do this, DO NOT specify a server_ip or a server_port when running the scripts. It will default to localhost and port 5555.
- 1 player can play the game alone
- the server and client scripts require Python 3.x to be installed on that machine.
- Ensure that the server IP and port are correctly set in both server and client scripts.
- Firewall setting may block connections on the server port (worked for me though)
