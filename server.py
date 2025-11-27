# Author: Nathan Gawargy (patched)
# Math Genius Game Server (fixed: remove disconnected clients properly)

import socket
import threading
import random
import struct
import time

# TOKENS (message TYPES)
# Client -> Server
JOIN = 1
START = 2
CLICK = 3
NAME_UPDATE = 4
PLAY_AGAIN = 5
CLIENT_LEFT = 6
# Server -> Client
WELCOME = 10
START_GAME = 11
CLICK_UPDATE = 12
GAME_OVER = 13
TIMER_START = 14
SCORE_UPDATE = 15
SERVER_BUSY = 16
PLAYER_LEFT_UPDATE_OTHERS = 17
PLAYER_ID_MAP = 18

def is_prime(n):
    if n < 2:
        return False
    if n == 2:
        return True
    if n % 2 == 0:
        return False
    for i in range(3, int(n**0.5) + 1, 2):
        if n % i == 0:
            return False
    return True

def generate_board():
    board = [['' for _ in range(5)] for _ in range(5)]
    primes = [i for i in range(2, 2000) if is_prime(i)]
    odd_numbers = [i for i in range(1, 2001, 2)]
    num_primes = random.randint(10, 15)

    positions = [(i, j) for i in range(5) for j in range(5)]
    random.shuffle(positions)
    selected = positions[:num_primes]

    for (i, j) in selected:
        board[i][j] = str(random.choice(primes))
    for i in range(5):
        for j in range(5):
            if board[i][j] == '':
                board[i][j] = str(random.choice(odd_numbers))
    return board

class ClientHandler:
    def __init__(self, client_socket, address, server, client_id):
        self.client_socket = client_socket
        self.address = address
        self.server = server
        self.client_id = client_id
        self.running = True
        self.player_name = None
        self.lock = threading.Lock()  # to avoid concurrent send/cleanup on same client

    def encode_message(self, msg_type, data):
        if isinstance(data, str):
            data_bytes = data.encode('utf-8')
        else:
            data_bytes = str(data).encode('utf-8')
        type_byte = struct.pack('B', msg_type)
        length_bytes = struct.pack('!I', len(data_bytes))
        return type_byte + length_bytes + data_bytes

    def decode_message(self, packet):
        msg_type = struct.unpack('B', packet[0:1])[0]
        length = struct.unpack('!I', packet[1:5])[0]
        data_bytes = packet[5:5+length]
        data = data_bytes.decode('utf-8')
        return msg_type, data

    def send_message(self, msg_type, data, broadcast=False):
        try:
            if broadcast:
                self.server.broadcast_message(msg_type, data)
                return
            packet = self.encode_message(msg_type, data)
            with self.lock:
                self.client_socket.send(packet)
            # optional debug:
            print(f"Sent to {self.address}: Type={msg_type}, Data={str(data)[:100]}")
        except Exception as e:
            print(f"Error sending message to {self.address}: {e}")
            # mark not running and trigger server-side cleanup
            self.running = False
            # cleanup will be handled by broadcast logic or by listen finally

    def listen(self):
        try:
            while self.running:
                header = self.client_socket.recv(5)
                if not header or len(header) < 5:
                    print(f"Client {self.address} disconnected (no header)")
                    break
                length = struct.unpack('!I', header[1:5])[0]
                data_bytes = b''
                while len(data_bytes) < length:
                    remaining = length - len(data_bytes)
                    chunk = self.client_socket.recv(remaining)
                    if not chunk:
                        raise ConnectionError(f"Connection closed. Expected {length} bytes, got {len(data_bytes)}")
                    data_bytes += chunk
                if len(data_bytes) != length:
                    raise ValueError(f"Data length mismatch: expected {length}, got {len(data_bytes)}")
                packet = header + data_bytes
                msg_type, data = self.decode_message(packet)
                print(f"Received from {self.address}: Type={msg_type}, Data={data}")
                self.handle_message(msg_type, data)
        except Exception as e:
            print(f"Error listening to {self.address}: {e}")
        finally:
            # ensure cleanup is always invoked
            try:
                self.cleanup()
            except Exception as e:
                print(f"Error during cleanup of {self.address}: {e}")

    def handle_message(self, msg_type, data):
        if msg_type == JOIN:
            # prevent duplicate names (only among current active players)
            active_names = set(self.server.player_names.get(c.client_id) for c in self.server.clients if c is not self and getattr(c, 'running', False) and c.player_name)
            if data in (n for n in active_names if n):
                self.send_message(SERVER_BUSY, "Name already in use. Choose another.")
                # close and cleanup
                self.running = False
                try:
                    with self.lock:
                        self.client_socket.close()
                except:
                    pass
                return

            self.player_name = data
            self.server.player_names[self.client_id] = data
            self.send_message(WELCOME, f"Welcome {self.player_name}! You are connected to the Math Game Server.")
            # notify all clients of player count
            player_count = len([c for c in self.server.clients if getattr(c, 'running', False) and c.player_name])
            self.server.broadcast_message(WELCOME, f"{player_count} player(s) connected. Waiting for game to start...")
        
        elif msg_type == NAME_UPDATE:
            self.player_name = data
            self.server.player_names[self.client_id] = data

        elif msg_type == PLAY_AGAIN:
            self.server.player_ready_for_new_game(self.client_id)

        elif msg_type == CLIENT_LEFT:
            # Client declared they are leaving after game
            self.server.player_left_after_game(self.client_id, self.player_name)
            # proactively cleanup this connection
            self.cleanup()

        elif msg_type == START:
            if not self.player_name:
                self.send_message(GAME_OVER, "Error: Please JOIN first before starting the game.")
                return
            if not self.server.game_started:
                self.server.mark_player_ready(self.client_id)
            else:
                self.send_message(CLICK_UPDATE, str(self.server.board))
        elif msg_type == CLICK:
            if not self.server.game_started:
                self.send_message(GAME_OVER, "Error: Game not started. Send START message first.")
                return
            parts = data.split(',')
            try:
                row = int(parts[0]); col = int(parts[1])
            except:
                return
            with self.server.board_lock:
                clicked_value = self.server.board[row][col]
                if clicked_value.startswith('o[') or clicked_value.startswith('x['):
                    return
                num_value = int(clicked_value)
                if is_prime(num_value):
                    self.server.board[row][col] = f"o[{self.client_id}]:{num_value}" # keep number value for client display
                    self.server.scores[self.client_id] = self.server.scores.get(self.client_id, 0) + 1
                else:
                    self.server.board[row][col] = f"x[{self.client_id}]:{num_value}" # keep number value for client display
                    self.server.scores[self.client_id] = self.server.scores.get(self.client_id, 0) - 1
                # broadcast updated board + scores
                self.server.broadcast_message(CLICK_UPDATE, str(self.server.board))
                score_data = self.server.format_scores()
                self.server.broadcast_message(SCORE_UPDATE, score_data)
                if self.server.check_board_complete():
                    self.server.end_game("BOARD_COMPLETE")
        else:
            self.send_message(GAME_OVER, f"Unknown message type: {msg_type}")

    def cleanup(self):
        # guard so cleanup is idempotent
        if not getattr(self, 'running', False) and not self.client_socket:
            # already cleaned up
            return
        self.running = False
        try:
            with self.lock:
                try:
                    self.client_socket.shutdown(socket.SHUT_RDWR)
                except:
                    pass
                try:
                    self.client_socket.close()
                except:
                    pass
        except Exception:
            pass

        # remove player data from server
        try:
            with self.server.clients_lock:
                if self in self.server.clients:
                    self.server.clients.remove(self)
        except Exception as e:
            print(f"Error removing client handler from server list: {e}")

        if self.client_id in self.server.player_names:
            try:
                del self.server.player_names[self.client_id]
            except KeyError:
                pass

        if self.client_id in self.server.scores:
            try:
                del self.server.scores[self.client_id]
            except KeyError:
                pass

        if hasattr(self.server, "ready_players"):
            try:
                self.server.ready_players.discard(self.client_id)
            except Exception:
                pass

        # Inform remaining clients that this player has left (so clients can update UI)
        try:
            if self.player_name:
                self.server.broadcast_message(PLAYER_LEFT_UPDATE_OTHERS, f"{self.player_name} has disconnected.")
        except Exception as e:
            print(f"Error broadcasting player-left: {e}")

        print(f"Connection with {self.address} (ID {self.client_id}) closed and cleaned up")
        self.server.check_force_end_game()

class MathGameServer:
    def __init__(self, host='localhost', port=5555):
        self.host = host
        self.port = port
        self.server_socket = None
        self.clients = []
        self.clients_lock = threading.Lock()
        self.running = False
        self.board = None
        self.game_started = False
        self.board_lock = threading.Lock()
        self.game_timer = None
        self.game_duration = 120
        self.scores = {}          # client_id -> score
        self.player_names = {}    # client_id -> player_name
        self.next_client_id = 1   # incremental id to avoid reuse

    def mark_player_ready(self, client_id):
        if not hasattr(self, "ready_players"):
            self.ready_players = set()

        # ensure client is active
        active_clients = [c for c in self.clients if getattr(c, 'running', False) and c.player_name]
        active_ids = {c.client_id for c in active_clients}
        if client_id not in active_ids:
            # ignore ready from non-active client
            return

        self.ready_players.add(client_id)
        ready_count = len(self.ready_players)
        total = len(active_clients)
        status = f"{ready_count}/{total} players ready"
        self.broadcast_message(WELCOME, status)

        if ready_count == total and total > 0:
            self.ready_players.clear()
            self.start_game()
            self.broadcast_message(TIMER_START, str(self.game_duration))
            self.broadcast_message(START_GAME, str(self.board))
            self.broadcast_message(SCORE_UPDATE, self.format_scores())
            self.broadcast_message(PLAYER_ID_MAP, self.format_player_id_map())
    
    def redistribute_client_ids(self):
        # Redistribute IDs on game end to accomodate new players for future games
        active_clients = [c for c in self.clients if c.running and c.player_name]

        # Assign new IDs
        new_id_map = {}
        new_player_names = {}
        new_scores = {}

        for new_id, client in enumerate(active_clients, start=1):
            old_id = client.client_id
            client.client_id = new_id
            new_id_map[old_id] = new_id
            new_player_names[new_id] = client.player_name
            new_scores[new_id] = 0  # reset scores for new round

        # Replace server dictionaries
        self.player_names = new_player_names
        self.scores = new_scores

        print("ID redistribution complete:", new_id_map)

    def start_game(self):
        self.redistribute_client_ids()
        self.board = generate_board()
        self.game_started = True
        with self.clients_lock:
            for client in list(self.clients):
                if client.player_name and client.running:
                    self.scores[client.client_id] = 0
        if self.game_timer and getattr(self.game_timer, 'is_alive', lambda: False)():
            try:
                self.game_timer.cancel()
            except:
                pass
        self.game_timer = threading.Timer(self.game_duration, self.end_game_timer)
        self.game_timer.daemon = True
        self.game_timer.start()
        print(f"Game started ====> Board generated. Timer: {self.game_duration}s")
        
    def check_force_end_game(self):
        # Kills current game in the event that someone leaves a game
        active = [c for c in self.clients if getattr(c, 'running', False) and c.player_name]
        if len(active) == 0 and self.game_started:
            print("All clients disconnected. Force-ending the game.")
            self.end_game("ALL_CLIENTS_DISCONNECTED")

    def broadcast_message(self, msg_type, data):
        # iterate over a shallow copy to allow pruning
        self.check_force_end_game()
        with self.clients_lock:
            clients_copy = list(self.clients)
        for client in clients_copy:
            if not getattr(client, 'running', False):
                # run cleanup to ensure removal
                try:
                    client.cleanup()
                except:
                    pass
                continue
            try:
                packet = client.encode_message(msg_type, data)
                with client.lock:
                    client.client_socket.send(packet)
                print(f"Broadcast to {client.address}: Type={msg_type}, Data={str(data)[:100]}")
            except Exception as e:
                print(f"Error broadcasting to {client.address}: {e}. Removing client.")
                # on failure remove that client
                try:
                    client.running = False
                    client.cleanup()
                except Exception as e2:
                    print(f"Error during client cleanup after failed broadcast: {e2}")

    def check_board_complete(self):
        if not self.board:
            return False
        for i in range(5):
            for j in range(5):
                value = self.board[i][j]
                if not value.startswith('o[') and not value.startswith('x['):
                    try:
                        num_value = int(value)
                        if is_prime(num_value):
                            return False
                    except ValueError:
                        pass
        return True

    def end_game_timer(self):
        print("Game timer expired!")
        self.end_game("TIME_UP")

    def format_scores(self):
        formatted = {}
        for client_id, score in self.scores.items():
            name = self.player_names.get(client_id, f"Player {client_id}")
            formatted[name] = score
        return str(formatted)
    
    def format_player_id_map(self):
        # returns mapping of client_id to player name
        return str(self.player_names)

    def player_ready_for_new_game(self, client_id):
        if not hasattr(self, 'ready_players'):
            self.ready_players = set()
        # only count active players
        active = [c for c in self.clients if getattr(c, 'running', False) and c.player_name]
        active_ids = {c.client_id for c in active}
        if client_id not in active_ids:
            return
        self.ready_players.add(client_id)
        ready_count = len(self.ready_players)
        total_players = len(active)
        print(f"Player {client_id} ready for new game. {ready_count}/{total_players} ready.")
        ready_names = [self.player_names.get(pid, f"Player {pid}") for pid in self.ready_players]
        status_msg = f"{ready_count}/{total_players} players ready: {', '.join(ready_names)}"
        self.broadcast_message(WELCOME, status_msg)
        if ready_count == total_players and total_players > 0:
            self.ready_players.clear()
            self.start_game()
            # send to all active clients
            self.broadcast_message(TIMER_START, str(self.game_duration))
            self.broadcast_message(START_GAME, str(self.board))
            self.broadcast_message(SCORE_UPDATE, self.format_scores())
            self.broadcast_message(PLAYER_ID_MAP, self.format_player_id_map())

    def player_left_after_game(self, client_id, player_name):
        if hasattr(self, 'ready_players') and client_id in self.ready_players:
            self.ready_players.discard(client_id)
        if hasattr(self, 'ready_players'):
            self.ready_players.clear()
        message = f"{player_name} has left the game and will not play again."
        self.broadcast_message(PLAYER_LEFT_UPDATE_OTHERS, message)
        print(f"Player {player_name} (ID: {client_id}) left after game ended.")

    def end_game(self, reason):
        if not self.game_started:
            return
        self.game_started = False
        if self.game_timer and getattr(self.game_timer, 'is_alive', lambda: False)():
            try:
                self.game_timer.cancel()
            except:
                pass
        if self.scores:
            winner_id = max(self.scores.items(), key=lambda x: x[1])[0]
            winner_name = self.player_names.get(winner_id, f"Player {winner_id}")
            winner_score = self.scores[winner_id]
            formatted_scores = self.format_scores()
            if reason == "TIME_UP":
                message = f"Time's up! Winner: {winner_name} with {winner_score} points. Final scores: {formatted_scores}"
            else:
                message = f"All primes found! Winner: {winner_name} with {winner_score} points. Final scores: {formatted_scores}"
        else:
            message = f"Game ended: {reason}"
        self.broadcast_message(GAME_OVER, message)
        print(f"Game ended: {message}")

    def start(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        try:
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(8)
            self.running = True
            print(f"Server started on {self.host}:{self.port}")
            self.accept_connections()
        except Exception as e:
            print(f"Error starting server: {e}")
        finally:
            self.stop()

    def accept_connections(self):
        while self.running:
            try:
                client_socket, address = self.server_socket.accept()
                print(f"New connection from {address}")
                if self.game_started:
                    reject_msg = "Connection rejected: Game is currently in progress. Please wait for the next game."
                    try:
                        data_bytes = reject_msg.encode('utf-8')
                        type_byte = struct.pack('B', SERVER_BUSY)
                        length_bytes = struct.pack('!I', len(data_bytes))
                        packet = type_byte + length_bytes + data_bytes
                        client_socket.send(packet)
                    except:
                        pass
                    client_socket.close()
                    print(f"Rejected connection from {address}: Game in progress")
                    continue

                with self.clients_lock:
                    client_id = self.next_client_id
                    self.next_client_id += 1
                client_handler = ClientHandler(client_socket, address, self, client_id)
                with self.clients_lock:
                    self.clients.append(client_handler)
                t = threading.Thread(target=client_handler.listen, daemon=True)
                t.start()
                print(f"Client {address} connected. Waiting for JOIN message... (ID {client_id})")
            except Exception as e:
                if self.running:
                    print(f"Error accepting connection: {e}")

    def stop(self):
        self.running = False
        with self.clients_lock:
            clients_copy = list(self.clients)
        for client in clients_copy:
            try:
                client.cleanup()
            except:
                pass
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
        print("Server stopped")

if __name__ == "__main__":
    server = MathGameServer(host='localhost', port=5555)
    try:
        server.start()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        server.stop()
