# Author: Nathan Gawargy
# Math Genius Game Server

import socket
import threading
import random
import struct

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

# Generate the board with 10 to 15 primes from 2-2000 and odd numbers everywhere else.
# Board is a 5x5 grid
def generate_board():
    board = [['' for _ in range(5)] for _ in range(5)]
    primes = [i for i in range(2, 2000) if is_prime(i)] # prime numbers from 2 to 2000
    odd_numbers = [i for i in range(1, 2001, 2)]        # odd numbers from 1 to 2000
    num_primes = random.randint(10, 15)
    
    positions = []
    for i in range(5):
        for j in range(5):
            positions.append((i, j))
    
    random.shuffle(positions)
    selected_positions = positions[:num_primes]
    
    # put the numbers in random positions on the board
    for pos in selected_positions:
        i, j = pos
        board[i][j] = str(random.choice(primes))
    for i in range(5):
        for j in range(5):
            if board[i][j] == '':
                board[i][j] = str(random.choice(odd_numbers))
    return board

# Client Handler to manage each connected client
# Used to also handle message encoding/decoding to send to/from client
# TYPE-LENGTH-DATA Message format:
#   Type (1 byte): integer indicating message type
#   Length (4 bytes): integer indicating length of data
#   Data (max 2^32 bytes): actual data 
class ClientHandler:    
    def __init__(self, client_socket, address, server, client_id):
        self.client_socket = client_socket
        self.address = address
        self.server = server
        self.client_id = client_id
        self.running = True
        self.player_name = None
    
    # Function to encode messages into bytes to send to client
    def encode_message(self, msg_type, data):
        # Convert data to bytes
        if isinstance(data, str):
            data_bytes = data.encode('utf-8')
        else:
            data_bytes = str(data).encode('utf-8')
        
        # TYPE 1 byte
        type_byte = struct.pack('B', msg_type)
        
        # LENGTH 4 bytes
        length = len(data_bytes)
        length_bytes = struct.pack('!I', length)
                
        packet = type_byte + length_bytes + data_bytes # DATA
        return packet
    
    # Function to decode messages from bytes received from client (separate into TYPE, DATA)
    def decode_message(self, packet):
        msg_type = struct.unpack('B', packet[0:1])[0] # TYPE
        length = struct.unpack('!I', packet[1:5])[0] # LENGTH
        data_bytes = packet[5:5+length] # DATA
        data = data_bytes.decode('utf-8')
        return msg_type, data
    
    # Function to send message to client (broadcast = True => send to all clients)
    def send_message(self, msg_type, data, broadcast=False):
        try:
            if broadcast:
                # Broadcast to all clients
                self.server.broadcast_message(msg_type, data)
            else:
                # Send only to this client
                packet = self.encode_message(msg_type, data)
                self.client_socket.send(packet)
                print(f"Sent to {self.address}: Type={msg_type}, Data={data[:100] if len(str(data)) > 100 else data}") # TODO: NATHAN remove this
        except Exception as e:
            print(f"Error sending message to {self.address}: {e}")
            self.running = False
    
    def listen(self):
        try:
            while self.running:
                header = self.client_socket.recv(5) 
                
                if not header or len(header) < 5:
                    print(f"Client {self.address} disconnected")
                    break
                
                # use length to know how much data to receive
                length = struct.unpack('!I', header[1:5])[0]
                
                # receive actual data
                data_bytes = b''
                while len(data_bytes) < length:
                    remaining = length - len(data_bytes)
                    chunk = self.client_socket.recv(remaining) # receive remaining bytes
                    if not chunk:
                        raise ConnectionError(f"Connection closed. Expected {length} bytes, got {len(data_bytes)}")
                    data_bytes += chunk
                
                if len(data_bytes) != length: # verify we got exactly the right amount
                    raise ValueError(f"Data length mismatch: expected {length}, got {len(data_bytes)}")
                
                # reconstruct full packet + decode
                packet = header + data_bytes
                msg_type, data = self.decode_message(packet)
                
                print(f"Received from {self.address}: Type={msg_type}, Data={data}") # TODO: NATHAN remove this
                
                # process the message
                self.handle_message(msg_type, data)
                
        except Exception as e:
            print(f"Error listening to {self.address}: {e}")
        finally:
            self.cleanup()
    
    # Function to handle messages from client (knows how to decode different TOKENS/TYPES)
    def handle_message(self, msg_type, data):
        # Message types:
        # Client to Server:
        #   JOIN = 1 (data: player_name)
        #   START = 2 (data: empty or game settings)
        #   CLICK = 3 (data: row,col position)
        # Server to Client:
        #   WELCOME = 10 (data: player info)
        #   START_GAME = 11 (data: board)
        #   CLICK_UPDATE = 12 (data: click result/board state)
        #   GAME_OVER = 13 (data: game result)
        
        if msg_type == JOIN:
            self.player_name = data
            # Store player name in server's player_names dict
            self.server.player_names[self.client_id] = data
            self.send_message(WELCOME, f"Welcome {self.player_name}! You are connected to the Math Game Server.")
            # Notify all clients about new player
            player_count = len([c for c in self.server.clients if c.player_name])
            self.send_message(WELCOME, f"{player_count} player(s) connected. Waiting for game to start...", broadcast=True)
            
        elif msg_type == NAME_UPDATE:
            # Update player name
            self.player_name = data
            self.server.player_names[self.client_id] = data
        
        elif msg_type == PLAY_AGAIN:
            # client wants to play again => use same clients
            self.server.player_ready_for_new_game(self.client_id)
        
        elif msg_type == CLIENT_LEFT:
            # client chose to exit instead of play again
            self.server.player_left_after_game(self.client_id, self.player_name)
            
        elif msg_type == START:
            if not self.player_name:
                self.send_message(GAME_OVER, "Error: Please JOIN first before starting the game.")
                return
            
            if not self.server.game_started: # start game
                self.server.start_game()
                # Send TIMER_START to all clients
                self.send_message(TIMER_START, str(self.server.game_duration), broadcast=True)
                # Send START_GAME to all clients with initial board
                self.send_message(START_GAME, str(self.server.board), broadcast=True)
                # Send initial scores
                score_data = self.server.format_scores()
                self.send_message(SCORE_UPDATE, score_data, broadcast=True)
            else: # game already started, send current board state as CLICK_UPDATE
                self.send_message(CLICK_UPDATE, str(self.server.board))
        elif msg_type == CLICK:
            if not self.server.game_started:
                self.send_message(GAME_OVER, "Error: Game not started. Send START message first.")
                return
            
            parts = data.split(',')
            row = int(parts[0])
            col = int(parts[1])
            
            with self.server.board_lock: # thread lock to prevent race conditions
                clicked_value = self.server.board[row][col]
                
                if clicked_value.startswith('o[') or clicked_value.startswith('x['):
                    return # if already clicked = ignore
                
                # TODO: NATHAN can put this in its own function
                ##############################
                num_value = int(clicked_value)
                if is_prime(num_value):
                    self.server.board[row][col] = f"o[{self.client_id}]" # add player marker (O means correct)
                    self.server.scores[self.client_id] = self.server.scores.get(self.client_id, 0) + 1 # add +1 to that client's score
                else:
                    self.server.board[row][col] = f"x[{self.client_id}]" # add player marker (X means wrong)
                    self.server.scores[self.client_id] = self.server.scores.get(self.client_id, 0) - 1 # subtract 1 from that client's score
                #############################

                # broadcast updated board + scores
                self.send_message(CLICK_UPDATE, str(self.server.board), broadcast=True)
                score_data = self.server.format_scores()
                self.send_message(SCORE_UPDATE, score_data, broadcast=True)
                
                # Check if board is complete
                if self.server.check_board_complete():
                    self.server.end_game("BOARD_COMPLETE")
                
        else:
            self.send_message(GAME_OVER, f"Unknown message type: {msg_type}")
    
    def cleanup(self):
        self.running = False
        self.client_socket.close()
        print(f"Connection with {self.address} closed")


class MathGameServer:    
    def __init__(self, host='localhost', port=5555):
        self.host = host
        self.port = port
        self.server_socket = None
        self.clients = []
        self.running = False
        # Shared game state
        self.board = None
        self.game_started = False
        self.board_lock = threading.Lock()  # THREAD SAFE board access
        # Timer and scoring
        self.game_timer = None
        self.game_duration = 120  # 2 minutes in seconds
        self.scores = {}  # client_id -> score
        self.player_names = {}  # client_id -> player_name
    
    def start_game(self):
        self.board = generate_board()
        self.game_started = True
        # Initialize scores for all connected clients
        for client in self.clients:
            if client.player_name:
                self.scores[client.client_id] = 0
        # Start game timer
        self.game_timer = threading.Timer(self.game_duration, self.end_game_timer)
        self.game_timer.daemon = True
        self.game_timer.start()
        print(f"Game started ====> Board generated. Timer: {self.game_duration}s")
    
    def broadcast_message(self, msg_type, data):
        for client in self.clients:
            if client.running:
                try:
                    packet = client.encode_message(msg_type, data)
                    client.client_socket.send(packet)
                    print(f"Broadcast to {client.address}: Type={msg_type}, Data={data[:100] if len(str(data)) > 100 else data}") # TODO: NATHAN remove this
                except Exception as e:
                    print(f"Error broadcasting to {client.address}: {e}")
    
    def check_board_complete(self):
        if not self.board:
            return False
        
        for i in range(5):
            for j in range(5):
                value = self.board[i][j]
                # If it's not marked (doesn't start with 'o[' or 'x['), check if it's a prime
                if not value.startswith('o[') and not value.startswith('x['):
                    try:
                        num_value = int(value)
                        if is_prime(num_value):
                            # Found an unmarked prime, game not complete
                            return False
                    except ValueError:
                        pass
        return True
    
    # Called when the game timer expires
    def end_game_timer(self):
        print("Game timer expired!")
        self.end_game("TIME_UP")
    
    # Used to format scores with player names instead of their IDs
    def format_scores(self):
        formatted = {}
        for client_id, score in self.scores.items():
            name = self.player_names.get(client_id, f"Player {client_id}")
            formatted[name] = score
        return str(formatted)
    
    # Function after ending a game to check which players want to play again
    # Only if ALL those connected players want to play again, the game restarts
    def player_ready_for_new_game(self, client_id):
        if not hasattr(self, 'ready_players'):
            self.ready_players = set()
        
        self.ready_players.add(client_id)
        ready_count = len(self.ready_players)
        total_players = len([c for c in self.clients if c.player_name])
        
        print(f"Player {client_id} ready for new game. {ready_count}/{total_players} ready.")
        
        # notify all clients about ready status
        ready_names = [self.player_names.get(pid, f"Player {pid}") for pid in self.ready_players]
        status_msg = f"{ready_count}/{total_players} players ready: {', '.join(ready_names)}"
        self.broadcast_message(WELCOME, status_msg)
        
        # start when all players are ready
        if ready_count == total_players and total_players > 0:
            self.ready_players.clear()
            self.start_game()
            # Start new game => send TIMER_START, START_GAME, SCORE_UPDATE
            for client in self.clients:
                if client.player_name:
                    client.send_message(TIMER_START, str(self.game_duration), broadcast=True)
                    client.send_message(START_GAME, str(self.board), broadcast=True)
                    score_data = self.format_scores()
                    client.send_message(SCORE_UPDATE, score_data, broadcast=True)
                    break
    
    # Notify other players when someone leaves instead of playing again
    def player_left_after_game(self, client_id, player_name):
        # remove from ready players if they were in there
        if hasattr(self, 'ready_players') and client_id in self.ready_players:
            self.ready_players.discard(client_id)
        
        # clear all ready players since we can't continue without all original players
        if hasattr(self, 'ready_players'):
            self.ready_players.clear()
        
        # notify all other clients
        message = f"{player_name} has left the game and will not play again."
        self.broadcast_message(PLAYER_LEFT_UPDATE_OTHERS, message)
        print(f"Player {player_name} (ID: {client_id}) left after game ended.")
    
    # Called to end the game and notify all clients
    # Happens when timer expires or board is complete or player found all primes
    # (could also end if server gets message which is not supported)
    def end_game(self, reason):
        if not self.game_started:
            return
        
        self.game_started = False
        
        if self.game_timer and self.game_timer.is_alive(): # stop timer (if still running)
            self.game_timer.cancel()
        
        # determine winner
        if self.scores:
            winner_id = max(self.scores.items(), key=lambda x: x[1])[0]
            winner_name = self.player_names.get(winner_id, f"Player {winner_id}")
            winner_score = self.scores[winner_id]
            
            formatted_scores = self.format_scores()
            if reason == "TIME_UP":
                message = f"Time's up! Winner: {winner_name} with {winner_score} points. Final scores: {formatted_scores}"
            else:  # BOARD_COMPLETE
                message = f"All primes found! Winner: {winner_name} with {winner_score} points. Final scores: {formatted_scores}"
        else:
            message = f"Game ended: {reason}"
        
        # broadcast GAME_OVER
        self.broadcast_message(GAME_OVER, message)
        print(f"Game ended: {message}")
    
    # START SERVER FUNCTION
    def start(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM) # TCP socket
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) # allow to bind the port again after program exit
        self.server_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1) # dont wait for packets to fill buffer, send right away
        
        try:
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(4)
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

                # check if game is already in progress
                if self.game_started:
                    reject_msg = "Connection rejected: Game is currently in progress. Please wait for the next game."
                    try:
                        # send rejection message (SERVER_BUSY)
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

                # create a client handler + associated unique ID
                client_id = len(self.clients) + 1
                client_handler = ClientHandler(client_socket, address, self, client_id)
                self.clients.append(client_handler)
                
                # start listening to the client in a separate thread
                client_thread = threading.Thread(target=client_handler.listen)
                client_thread.daemon = True
                client_thread.start()
                
                print(f"Client {address} connected. Waiting for JOIN message...")
                
            except Exception as e:
                if self.running:
                    print(f"Error accepting connection: {e}")
    
    def stop(self):
        self.running = False
        # close all client connections
        for client in self.clients:
            client.cleanup()
        if self.server_socket:
            self.server_socket.close()
        print("Server stopped")

if __name__ == "__main__":
    server = MathGameServer(host='localhost', port=5555)
    try:
        server.start()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        server.stop()
