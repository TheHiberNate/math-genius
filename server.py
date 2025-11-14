import socket
import threading
import random
import struct

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
        self.board = None
        self.game_started = False
    
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
    
    def decode_message(self, packet):
        msg_type = struct.unpack('B', packet[0:1])[0] # TYPE
        length = struct.unpack('!I', packet[1:5])[0] # LENGTH
        data_bytes = packet[5:5+length] # DATA
        data = data_bytes.decode('utf-8')
        return msg_type, data
    
    def send_message(self, msg_type, data, broadcast=False):
        try:
            if broadcast:
                # Broadcast to all clients
                self.server.broadcast_message(msg_type, data, exclude=self)
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
    
    def handle_message(self, msg_type, data):
        # Message types:
        # Client to Server:
        #   1 = JOIN (data: player_name)
        #   2 = START (data: empty or game settings)
        #   3 = CLICK (data: row,col position)
        # Server to Client:
        #   10 = WELCOME (data: player info)
        #   11 = START_GAME (data: board)
        #   12 = CLICK_UPDATE (data: click result/board state)
        #   13 = GAME_OVER (data: game result)
        
        if msg_type == 1:  # JOIN
            self.player_name = data
            self.send_message(10, f"Welcome {self.player_name}! You are connected to the Math Game Server.")
            # TODO: NATHAN need timer + notification of how many players are connected
            
        elif msg_type == 2:  # START
            if not self.player_name:
                self.send_message(13, "Error: Please JOIN first before starting the game.")
                return
            
            self.board = generate_board()
            self.game_started = True
            self.send_message(12, str(self.board), broadcast=True)
            
        elif msg_type == 3:  # CLICK
            if not self.game_started:
                self.send_message(13, "Error: Game not started. Send START message first.")
                return
            
            parts = data.split(',')
            row = int(parts[0])
            col = int(parts[1])
            
            clicked_value = self.board[row][col]
            
            if clicked_value.startswith('o[') or clicked_value.startswith('x['):
                return
            num_value = int(clicked_value)
            if is_prime(num_value):
                # update board with player marker
                self.board[row][col] = f"o[{self.client_id}]"
                self.send_message(12, str(self.board), broadcast=True) # TODO: NATHAN need SCORE update here
            else:
                self.board[row][col] = f"x[{self.client_id}]"
                self.send_message(12, str(self.board), broadcast=True)
                
        else:
            self.send_message(13, f"Unknown message type: {msg_type}")
    
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
    
    def broadcast_message(self, msg_type, data):
        for client in self.clients:
            if client.running:
                try:
                    packet = client.encode_message(msg_type, data)
                    client.client_socket.send(packet)
                    print(f"Broadcast to {client.address}: Type={msg_type}, Data={data[:100] if len(str(data)) > 100 else data}") # TODO: NATHAN remove this
                except Exception as e:
                    print(f"Error broadcasting to {client.address}: {e}")
    
    def start(self):
        """Start the server."""
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
