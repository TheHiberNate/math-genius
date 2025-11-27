# Author: Nathan Gawargy
# Math Genius Game Client

import socket
import threading
import struct
import tkinter as tk
from tkinter import messagebox, simpledialog

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


class MathGameClient:
    def __init__(self):
        self.socket = None
        self.running = False
        self.player_name = None
        self.board = None
        self.connected = False
        self.current_overlay = None  # track current overlay to destroy when needed
        self.id_to_name_map = {}  # map client IDs to player names
        self.my_client_id = None  # track our own client ID
        
        # GUI with Tkinter
        self.root = tk.Tk()
        self.root.title("Math Genius")
        self.root.geometry("600x700")
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # status label for connection status
        self.status_label = tk.Label(self.root, text="Not connected", font=("Arial", 12), pady=10)
        self.status_label.pack()
        
        # timer and Score
        self.info_frame = tk.Frame(self.root)
        self.info_frame.pack(pady=5)
        self.timer_label = tk.Label(self.info_frame, text="Time: --:--", font=("Arial", 14, "bold"), fg="blue")
        self.timer_label.pack(side=tk.LEFT, padx=20)
        self.score_label = tk.Label(self.info_frame, text="Scores: ", font=("Arial", 12))
        self.score_label.pack(side=tk.LEFT, padx=20)
        
        # Legend for colors
        self.legend_frame = tk.Frame(self.root, bg="white", relief=tk.RIDGE, borderwidth=2)
        self.legend_frame.pack(pady=5)
        tk.Label(self.legend_frame, text="Color Legend:", font=("Arial", 10, "bold"), bg="white").pack(side=tk.LEFT, padx=5)
        
        # Green legend
        green_box = tk.Label(self.legend_frame, text="  ", bg="lightgreen", relief=tk.RAISED, borderwidth=1)
        green_box.pack(side=tk.LEFT, padx=2)
        tk.Label(self.legend_frame, text="Your correct", font=("Arial", 9), bg="white").pack(side=tk.LEFT, padx=(0, 10))
        
        # Blue legend
        blue_box = tk.Label(self.legend_frame, text="  ", bg="lightblue", relief=tk.RAISED, borderwidth=1)
        blue_box.pack(side=tk.LEFT, padx=2)
        tk.Label(self.legend_frame, text="Opponent correct", font=("Arial", 9), bg="white").pack(side=tk.LEFT, padx=(0, 10))
        
        # Red legend
        red_box = tk.Label(self.legend_frame, text="  ", bg="lightcoral", relief=tk.RAISED, borderwidth=1)
        red_box.pack(side=tk.LEFT, padx=2)
        tk.Label(self.legend_frame, text="Your wrong", font=("Arial", 9), bg="white").pack(side=tk.LEFT, padx=(0, 10))
        
        # Orange legend
        orange_box = tk.Label(self.legend_frame, text="  ", bg="orange", relief=tk.RAISED, borderwidth=1)
        orange_box.pack(side=tk.LEFT, padx=2)
        tk.Label(self.legend_frame, text="Opponent wrong", font=("Arial", 9), bg="white").pack(side=tk.LEFT, padx=(0, 10))
        
        # timer state
        self.timer_running = False
        self.time_remaining = 0
        
        # buttons on the TKINTER window
        self.control_frame = tk.Frame(self.root)
        self.control_frame.pack(pady=10)
        self.connect_btn = tk.Button(self.control_frame, text="Connect", command=self.connect_to_server, 
                                     font=("Arial", 12), bg="green", fg="white", width=12)
        self.connect_btn.pack(side=tk.LEFT, padx=5)
        self.start_btn = tk.Button(self.control_frame, text="Ready Up", command=self.send_start, 
                                   font=("Arial", 12), bg="blue", fg="white", width=12, state=tk.DISABLED)
        self.start_btn.pack(side=tk.LEFT, padx=5)
        self.disconnect_btn = tk.Button(
            self.control_frame, text="Disconnect",
            command=self.exit_to_home,
            font=("Arial", 12), bg="red", fg="white", width=12, state=tk.DISABLED)
        self.disconnect_btn.pack(side=tk.LEFT, padx=5)

        self.board_frame = tk.Frame(self.root, bg="white", relief=tk.RAISED, borderwidth=2) # game board frame
        self.board_frame.pack(pady=20)
        
        # create 5x5 grid of buttons
        self.board_buttons = []
        for i in range(5):
            row = []
            for j in range(5):
                btn = tk.Button(self.board_frame, text="", width=10, height=3, 
                               font=("Arial", 14, "bold"),
                               command=lambda r=i, c=j: self.on_cell_click(r, c))
                btn.grid(row=i, column=j, padx=2, pady=2)
                btn.config(state=tk.DISABLED)
                row.append(btn)
            self.board_buttons.append(row)
        
        # message log
        self.log_frame = tk.Frame(self.root)
        self.log_frame.pack(pady=10, fill=tk.BOTH, expand=True)
        tk.Label(self.log_frame, text="Messages:", font=("Arial", 10, "bold")).pack(anchor=tk.W)
        self.log_text = tk.Text(self.log_frame, height=8, width=70, font=("Arial", 9))
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar = tk.Scrollbar(self.log_frame, command=self.log_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.config(yscrollcommand=scrollbar.set)
        
    def log_message(self, message):
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
    
    # Function to start countdown timer
    def start_timer(self, duration):
        self.time_remaining = duration
        self.timer_running = True
        self.update_timer_display()

    # Function to update timer display (client-side only)
    def update_timer_display(self):
        if self.timer_running and self.time_remaining > 0:
            minutes = self.time_remaining // 60
            seconds = self.time_remaining % 60
            self.timer_label.config(text=f"Time: {minutes:02d}:{seconds:02d}")
            self.time_remaining -= 1
            self.root.after(1000, self.update_timer_display)
        elif self.timer_running and self.time_remaining <= 0:
            self.timer_label.config(text="Time: 00:00", fg="red")
            self.timer_running = False
    
    # Function to update score display based on server msg
    def update_scores(self, scores_str):
        try:
            import ast
            scores = ast.literal_eval(scores_str)
            # scores output as "NameClient1: 5, NameClient2: 3"
            score_text = ", ".join([f"{name}: {score}" for name, score in sorted(scores.items())])
            self.score_label.config(text=f"Scores: {score_text}")
        except Exception as e:
            self.log_message(f"Error updating scores: {e}")
    
    # Function to update player ID mapping from score updates
    def update_player_id_map(self, map_str):
        try:
            import ast
            # map is sent as => {client_id: "Player Name", ...}
            id_map = ast.literal_eval(map_str)
            self.id_to_name_map = id_map
            
            # find the player's actual client ID by matching the player name
            for client_id, name in id_map.items():
                if name == self.player_name:
                    self.my_client_id = client_id
                    #self.log_message(f"client ID is: {client_id}")
                    break
        except Exception as e:
            self.log_message(f"Error updating player ID map: {e}")
    
    # Function to check if a client ID belongs to this player (used for displaying right colours on the board)
    def is_my_client_id(self, client_id):
        return self.my_client_id is not None and client_id == self.my_client_id
    
    # Function to encode messages into bytes to send to server
    def encode_message(self, msg_type, data):
        if isinstance(data, str):
            data_bytes = data.encode('utf-8')
        else:
            data_bytes = str(data).encode('utf-8')
        
        type_byte = struct.pack('B', msg_type)
        length = len(data_bytes)
        length_bytes = struct.pack('!I', length)
        
        packet = type_byte + length_bytes + data_bytes
        return packet
    
    # Function to decode messages from bytes received from server
    def decode_message(self, packet):
        msg_type = struct.unpack('B', packet[0:1])[0]
        length = struct.unpack('!I', packet[1:5])[0]
        data_bytes = packet[5:5+length]
        data = data_bytes.decode('utf-8')
        return msg_type, data
    
    # Function to connect to server
    # It connects with TCP to server and sends JOIN message (Type 1) with player name.
    # Considered only CONNECTED once the WELCOME message is received from server.
    def connect_to_server(self):
        if self.connected:
            messagebox.showinfo("Info", "Already connected to server")
            return
        
        # get player name
        name = simpledialog.askstring("Player Name", "Enter your name:", parent=self.root)
        if not name:
            return
        
        self.player_name = name
        
        try:
            # connect to server
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect(('localhost', 5555)) # TODO: NATHAN change this to actual ip/port later
            self.running = True
            
            # send JOIN message with the player name
            packet = self.encode_message(JOIN, self.player_name)
            self.socket.send(packet)
            
            self.log_message(f"Connecting as {self.player_name}...")
            self.status_label.config(text=f"Waiting for server response...", fg="orange")
            
            # start listener thread (will set connected=True when WELCOME received)
            listener_thread = threading.Thread(target=self.listen_to_server, daemon=True)
            listener_thread.start()
            
        except Exception as e:
            messagebox.showerror("Connection Error", f"Failed to connect: {e}")
            self.connected = False
            
    # Function to send START game message
    # Can be started by any of the clients connected
    # Game only starts when server sends back START_GAME (Type 11) message
    def send_start(self):
        if not self.connected:
            messagebox.showwarning("Warning", "Not connected to server")
            return
        try:
            packet = self.encode_message(START, "")
            self.socket.send(packet)
            self.log_message("Sent START game request. Waiting for server...")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to send START: {e}")
            
    # Function to handle cell click (sends message to server)
    def on_cell_click(self, row, col):
        if not self.connected:
            return
        
        try:
            # Send CLICK message with row,col
            click_data = f"{row},{col}"
            packet = self.encode_message(CLICK, click_data)
            self.socket.send(packet)
            self.log_message(f"Clicked cell ({row},{col})")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to send click: {e}")
            
    # Client listener thread
    def listen_to_server(self):
        try:
            while self.running:
                # Read header (5 bytes)
                header = self.socket.recv(5)
                if not header or len(header) < 5:
                    self.log_message("Disconnected from server")
                    break
                
                # Extract length
                length = struct.unpack('!I', header[1:5])[0]
                
                # Read data
                data_bytes = b''
                while len(data_bytes) < length:
                    remaining = length - len(data_bytes)
                    chunk = self.socket.recv(remaining)
                    if not chunk:
                        raise ConnectionError(f"Connection closed. Expected {length} bytes, got {len(data_bytes)}")
                    data_bytes += chunk
                
                # Decode message
                packet = header + data_bytes
                msg_type, data = self.decode_message(packet)
                
                # Handle message on GUI thread
                self.root.after(0, self.handle_server_message, msg_type, data)
                
        except Exception as e:
            self.log_message(f"Connection error: {e}")
            self.root.after(0, self.on_disconnect)
            
    # Function to handle messages from server
    def handle_server_message(self, msg_type, data):
        # Message types from server:
        #   WELCOME = 10
        #   START_GAME = 11 (initial board state)
        #   CLICK_UPDATE = 12 (board state)
        #   GAME_OVER = 13
        #   TIMER_START = 14
        #   SCORE_UPDATE = 15
        #   SERVER_BUSY = 16
        
        if msg_type == WELCOME:
            self.log_message(f"Server: {data}")
            # connected ONLY after WELCOME msg received
            if not self.connected:
                self.connected = True
                self.log_message(f"Successfully connected as {self.player_name}")
                self.status_label.config(text=f"Connected as {self.player_name}", fg="green")
                self.connect_btn.config(state=tk.DISABLED)
                self.start_btn.config(state=tk.NORMAL)
                self.disconnect_btn.config(state=tk.NORMAL)
        elif msg_type == TIMER_START: # start timer for specified duration
            duration = int(data)
            self.log_message(f"Game timer started: {duration} seconds")
            self.start_timer(duration)
        elif msg_type == START_GAME:
            self.log_message(f"Game started + Board received")
            self.status_label.config(text=f"Connected as {self.player_name}", fg="green")
            self.update_board(data)
            self.start_btn.config(state=tk.DISABLED) # hide start btn cuz game started already
        elif msg_type == CLICK_UPDATE:
            self.log_message(f"Board updated")
            self.update_board(data)
        elif msg_type == SCORE_UPDATE:
            self.update_scores(data)
        elif msg_type == PLAYER_ID_MAP:
            self.update_player_id_map(data)
        elif msg_type == SERVER_BUSY:
            self.log_message(f"Server Busy: {data}")
            messagebox.showerror("Connection Rejected", data)
            self.on_disconnect()
            self.disconnect_btn.config(state=tk.DISABLED)
        elif msg_type == PLAYER_LEFT_UPDATE_OTHERS:
            self.log_message(f"Player Left: {data}")
            self.show_player_left_overlay(data)
        elif msg_type == GAME_OVER:
            self.timer_running = False # update timer flag
            self.log_message(f"Game Over: {data}")
            
            # Parse game over message to display formatted results on board
            try:
                import ast
                # check if message contains scores = this means game ended normally
                if "Final scores:" in data:
                    parts = data.split("Final scores:")
                    winner_info = parts[0].strip()
                    scores_str = parts[1].strip()
                    scores = ast.literal_eval(scores_str)
        
                    # Display game over overlay on board
                    self.show_game_over_overlay(winner_info, scores)
                else:
                    messagebox.showinfo("Game Over", data)
            except:
                # Fallback to simple display if parsing fails
                messagebox.showinfo("Game Over", data)
    
    # Function to update the GUI board based on updates from server
    def update_board(self, board_str):
        try:
            import ast
            import re
            board = ast.literal_eval(board_str) # convert string board to python list
            self.board = board
            
            # update each entry
            for i in range(5):
                for j in range(5):
                    value = board[i][j]
                    btn = self.board_buttons[i][j]
                    
                    if btn['state'] == tk.DISABLED:
                        btn.config(state=tk.NORMAL)
                    
                    if value.startswith('o['): # prime found (correct answer)
                        match = re.search(r'o\[(\d+)\]:(\d+)', value) # extract client id from value like o[1]:___
                        if match:
                            client_id = int(match.group(1))
                            number = match.group(2)
                            # GREEN if this client got it, BLUE if opponent got it
                            if self.is_my_client_id(client_id):
                                btn.config(text=number, bg="lightgreen", fg="black")
                            else:
                                btn.config(text=number, bg="lightblue", fg="black")
                        else:
                            btn.config(text=value, bg="lightgreen", fg="black")
                    elif value.startswith('x['): # not prime clicked (wrong answer)
                        match = re.search(r'x\[(\d+)\]:(\d+)', value) # extract client id from value like x[1]:___
                        if match:
                            client_id = int(match.group(1))
                            number = match.group(2)
                            # RED if this client got it wrong, ORANGE if opponent got it wrong
                            if self.is_my_client_id(client_id):
                                btn.config(text=number, bg="lightcoral", fg="black")
                            else:
                                btn.config(text=number, bg="orange", fg="black")
                        else:
                            btn.config(text=value, bg="lightcoral", fg="black")
                    else: # box not clicked yet
                        btn.config(text=value, bg="lightgray", fg="black")    
        except Exception as e:
            self.log_message(f"Error updating board: {e}")
    
    # Create a frame overlay on top of the board to show results of the game
    def show_game_over_overlay(self, winner_info, scores):
        # destroy any existing overlay first
        if self.current_overlay:
            self.current_overlay.destroy()
        
        overlay = tk.Frame(self.board_frame, bg="white", relief=tk.RAISED, borderwidth=5)
        overlay.place(relx=0.5, rely=0.5, anchor=tk.CENTER, width=450, height=350)
        self.current_overlay = overlay  # Store reference
        
        title_label = tk.Label(overlay, text="GAME OVER", font=("Arial", 20, "bold"), bg="white", fg="darkblue")
        title_label.pack(pady=15)
        
        # Winner info and Standings
        winner_label = tk.Label(overlay, text=winner_info, font=("Arial", 14, "bold"),bg="white", fg="darkgreen", wraplength=400)
        winner_label.pack(pady=10)
        separator = tk.Frame(overlay, height=2, bg="darkblue")
        separator.pack(fill=tk.X, padx=20, pady=10)
        standings_label = tk.Label(overlay, text="Final Standings", font=("Arial", 16, "bold"), bg="white", fg="darkblue")
        standings_label.pack(pady=5)        
        scores_frame = tk.Frame(overlay, bg="white")
        scores_frame.pack(pady=10)
        
        # display each player's score
        for i, (name, score) in enumerate(sorted(scores.items(), key=lambda x: x[1], reverse=True)):
            medal = "FIRST" if i == 0 else "SECOND" if i == 1 else "THIRD" if i == 2 else "  "
            score_label = tk.Label(scores_frame, text=f"{medal} {name}: {score} points", 
                                   font=("Arial", 12), bg="white", fg="black")
            score_label.pack(anchor=tk.W, padx=20, pady=3)
        
        # btns for Exit and Play Again
        button_frame = tk.Frame(overlay, bg="white")
        button_frame.pack(pady=15)
        
        # Exit button == disconnect and return to home
        exit_btn = tk.Button(button_frame, text="Exit", 
                            command=lambda: [overlay.destroy(), setattr(self, 'current_overlay', None), self.exit_to_home()],
                            font=("Arial", 12), bg="red", fg="white", width=12)
        exit_btn.pack(side=tk.LEFT, padx=5)
        
        # Play Again == queue for new game with the same ppl
        play_again_btn = tk.Button(button_frame, text="Play Again", 
                                   command=lambda: [overlay.destroy(), setattr(self, 'current_overlay', None), self.request_play_again()],
                                   font=("Arial", 12), bg="green", fg="white", width=12)
        play_again_btn.pack(side=tk.LEFT, padx=5)
    
    # Show new display if a player doesn't want to play again (only option is to QUIT/EXIT)
    def show_player_left_overlay(self, message):
        # Destroy any existing overlay (like game over) to prevent interaction
        if self.current_overlay:
            self.current_overlay.destroy()
        
        overlay = tk.Frame(self.board_frame, bg="lightyellow", relief=tk.RAISED, borderwidth=5)
        overlay.place(relx=0.5, rely=0.5, anchor=tk.CENTER, width=400, height=200)
        self.current_overlay = overlay  # Store reference
        
        title_label = tk.Label(overlay, text="Player Left - Game Ended", font=("Arial", 18, "bold"), 
                               bg="lightyellow", fg="darkred")
        title_label.pack(pady=20)
        
        message_label = tk.Label(overlay, text=message, font=("Arial", 12), 
                            bg="lightyellow", fg="black", wraplength=350)
        message_label.pack(pady=10)

        info_label = tk.Label(overlay, text="The game cannot continue (because a player left). Please exit.", 
            font=("Arial", 10, "italic"), bg="lightyellow", fg="darkred")
        info_label.pack(pady=5)
        
        # EXIT button
        exit_btn = tk.Button(overlay, text="Exit to Home", 
                            command=lambda: [overlay.destroy(), setattr(self, 'current_overlay', None), self.exit_to_home()],
                            font=("Arial", 12), bg="red", fg="white", width=15)
        exit_btn.pack(pady=5)
    
    # Function to exit to home screen (disconnect from server)
    def exit_to_home(self):
        self.log_message("Exiting to home screen...")
        # notify server that this client is leaving
        if self.socket and self.connected:
            try:
                packet = self.encode_message(CLIENT_LEFT, "")
                self.socket.send(packet)
            except:
                pass
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
        self.on_disconnect()
        self.disconnect_btn.config(state=tk.DISABLED)
    
    # Function to request play again
    def request_play_again(self):
        if not self.connected:
            messagebox.showwarning("Warning", "Not connected to server")
            return
        
        try:
            packet = self.encode_message(PLAY_AGAIN, "")
            self.socket.send(packet)
            self.log_message("Ready for new game. Waiting for other players...")
            self.status_label.config(text="Waiting for other players...", fg="orange")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to request play again: {e}")
    
    def on_disconnect(self):
        self.connected = False
        self.running = False
        self.timer_running = False
        self.time_remaining = 0
        self.timer_label.config(text="Time: --:--", fg="blue")
        self.score_label.config(text="Scores:")
        self.status_label.config(text="Disconnected", fg="red")
        self.connect_btn.config(state=tk.NORMAL)
        self.start_btn.config(state=tk.DISABLED)
        for i in range(5):
            for j in range(5):
                self.board_buttons[i][j].config(state=tk.DISABLED) # Disable all board buttons

    def on_closing(self):
        self.running = False
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
        self.root.destroy()
        
    def run(self):
        self.root.mainloop() # used to start TKinter GUI


if __name__ == "__main__":
    client = MathGameClient()
    client.run()
