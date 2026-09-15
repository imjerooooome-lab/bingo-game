import random
import uuid
import os
import time
from flask import Flask, render_template_string, request, jsonify, redirect

app = Flask(__name__)

game_state = {
    'called_numbers': [],
    'remaining_numbers': list(range(1, 76)),
    'cards': {},
    'marked': {},
    'sessions': {},
    'session_names': {},
    'last_seen': {},
    'winner': None,
    'game_over': False,
    'price_per_card': 1,
    'current_pattern': 'straight'
}

def get_ball_letter(num):
    if num <= 15: return 'B'
    if num <= 30: return 'I'
    if num <= 45: return 'N'
    if num <= 60: return 'G'
    return 'O'

def get_total_pot():
    total_cards = sum(len(cards) for cards in game_state['sessions'].values())
    return total_cards * game_state['price_per_card']

def generate_card():
    ranges = [(1, 15), (16, 30), (31, 45), (46, 60), (61, 75)]
    card = []
    for start, end in ranges:
        col = random.sample(range(start, end + 1), 5)
        card.append(col)
    card = [list(row) for row in zip(*card)]
    card[2][2] = 0
    return card

def check_straight(marked_set, card_grid):
    for row in card_grid:
        if all(num in marked_set for num in row): return True
    for col in zip(*card_grid):
        if all(num in marked_set for num in col): return True
    if all(card_grid[i][i] in marked_set for i in range(5)): return True
    if all(card_grid[i][4-i] in marked_set for i in range(5)): return True
    return False

def check_4_sides(marked_set, card_grid):
    for i in range(5):
        if card_grid[0][i] not in marked_set: return False
        if card_grid[4][i] not in marked_set: return False
        if card_grid[i][0] not in marked_set: return False
        if card_grid[i][4] not in marked_set: return False
    return True

def check_parallel(marked_set, card_grid):
    rows = sum(1 for row in card_grid if all(num in marked_set for num in row))
    if rows >= 2: return True
    cols = sum(1 for col in zip(*card_grid) if all(num in marked_set for num in col))
    if cols >= 2: return True
    diag1 = all(card_grid[i][i] in marked_set for i in range(5))
    diag2 = all(card_grid[i][4-i] in marked_set for i in range(5))
    if diag1 and diag2: return True
    return False

def check_cross(marked_set, card_grid):
    if all(card_grid[i][i] in marked_set for i in range(5)) and all(card_grid[i][4-i] in marked_set for i in range(5)):
        return True
    return False

def check_blackout(marked_set, card_grid):
    for row in card_grid:
        for num in row:
            if num != 0 and num not in marked_set:
                return False
    return True

def check_bingo(marked_set, card_grid):
    marked_set.add(0)
    pattern = game_state['current_pattern']
    if pattern == 'straight': return check_straight(marked_set, card_grid)
    if pattern == '4sides': return check_4_sides(marked_set, card_grid)
    if pattern == 'parallel': return check_parallel(marked_set, card_grid)
    if pattern == 'cross': return check_cross(marked_set, card_grid)
    if pattern == 'blackout': return check_blackout(marked_set, card_grid)
    return False

def cleanup_dead_sessions():
    current_time = time.time()
    dead_sessions = []
    for sid, last_time in game_state['last_seen'].items():
        if current_time - last_time > 15:
            dead_sessions.append(sid)
    for sid in dead_sessions:
        print(f"Removing dead session: {sid}")
        if sid in game_state['sessions']:
            for card_id in game_state['sessions'][sid]:
                if card_id in game_state['cards']: del game_state['cards'][card_id]
                if card_id in game_state['marked']: del game_state['marked'][card_id]
            del game_state['sessions'][sid]
        if sid in game_state['session_names']: del game_state['session_names'][sid]
        if sid in game_state['last_seen']: del game_state['last_seen'][sid]

HOST_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Bingo Host</title>
    <style>
        * { box-sizing: border-box; }
        body { font-family: 'Segoe UI', sans-serif; text-align: center; background: linear-gradient(135deg, #1a1a2e, #16213e); color: white; padding: 20px; min-height: 100vh; margin: 0; }
        h1 { color: #ffd700; text-shadow: 2px 2px 4px rgba(0,0,0,0.5); font-size: 2.2rem; margin-bottom: 5px; }
        .pot-container { margin: 15px auto; max-width: 350px; }
        .pot-display { background: linear-gradient(135deg, #ffd700, #ff8c00); color: #1a1a2e; padding: 15px 30px; border-radius: 15px; box-shadow: 0 0 25px rgba(255, 215, 0, 0.4), inset 0 0 10px rgba(255,255,255,0.5); border: 2px solid #fff; }
        .pot-label { font-size: 1rem; font-weight: 900; letter-spacing: 2px; text-transform: uppercase; }
        .pot-amount { font-size: 3rem; font-weight: 900; line-height: 1; text-shadow: 1px 1px 2px rgba(255,255,255,0.5); }
        .mode-container { margin: 20px auto; max-width: 600px; display: flex; flex-wrap: wrap; justify-content: center; gap: 10px; }
        .mode-btn { padding: 12px 20px; font-size: 1rem; border: 2px solid rgba(255,255,255,0.2); border-radius: 10px; cursor: pointer; font-weight: bold; color: white; background: rgba(255,255,255,0.05); transition: all 0.2s; }
        .mode-btn:hover { background: rgba(255,255,255,0.1); }
        .mode-btn.active { background: linear-gradient(135deg, #ffd700, #ff8c00); color: #1a1a2e; border-color: #fff; box-shadow: 0 0 15px rgba(255, 215, 0, 0.5); }
        .mode-btn.blackout-2 { border-color: #4CAF50; }
        .mode-btn.blackout-2.active { background: linear-gradient(135deg, #4CAF50, #2e7d32); color: white; box-shadow: 0 0 15px rgba(76,175,80,0.5); }
        .mode-btn.blackout-5 { border-color: #f44336; }
        .mode-btn.blackout-5.active { background: linear-gradient(135deg, #f44336, #c62828); color: white; box-shadow: 0 0 15px rgba(244,67,54,0.5); }
        .pattern-section { margin: 20px auto; max-width: 700px; }
        .pattern-title { color: #ffd700; font-size: 1.1rem; margin-bottom: 10px; font-weight: bold; letter-spacing: 1px; }
        .pattern-container { display: flex; flex-wrap: wrap; justify-content: center; gap: 10px; align-items: center; }
        .pattern-btn { padding: 10px 15px; font-size: 0.9rem; border: 2px solid rgba(255,255,255,0.2); border-radius: 8px; cursor: pointer; font-weight: bold; color: white; background: rgba(255,255,255,0.05); transition: all 0.2s; }
        .pattern-btn:hover { background: rgba(255,255,255,0.1); }
        .pattern-btn.active { background: linear-gradient(135deg, #9c27b0, #6a1b9a); color: white; border-color: #e1bee7; box-shadow: 0 0 15px rgba(156,39,176,0.5); }
        .pattern-btn.blackout-btn { background: linear-gradient(135deg, #ff0000, #990000); color: white; border-color: #ff6666; }
        .pattern-btn.blackout-btn.active { background: linear-gradient(135deg, #ff0000, #990000); color: white; border-color: #ff6666; box-shadow: 0 0 15px rgba(255,0,0,0.5); }
        .pattern-preview { display: grid; grid-template-columns: repeat(5, 1fr); gap: 3px; background: #333; padding: 6px; border-radius: 8px; width: 80px; border: 2px solid #ffd700; box-shadow: 0 0 10px rgba(255,215,0,0.3); }
        .p-cell { width: 100%; aspect-ratio: 1; background: rgba(255,255,255,0.1); border-radius: 2px; }
        .p-cell.active { background: #ffd700; box-shadow: 0 0 5px #ffd700; }
        .p-cell.free { background: #ff9800; }
        .stage { display: flex; flex-wrap: wrap; justify-content: center; align-items: flex-start; gap: 20px; margin: 20px auto; max-width: 1200px; }
        .machine-column { display: flex; flex-direction: column; align-items: center; min-width: 260px; }
        .cage-wrapper { position: relative; width: 220px; height: 220px; }
        .cage { width: 220px; height: 220px; border-radius: 50%; background: radial-gradient(circle at 35% 35%, #666, #222 70%); border: 10px solid #aaa; box-shadow: 0 0 30px rgba(255,215,0,0.3), inset 0 0 40px rgba(0,0,0,0.6); position: relative; overflow: hidden; }
        .cage::after { content: ''; position: absolute; top: 10%; left: 15%; width: 35%; height: 20%; background: radial-gradient(ellipse, rgba(255,255,255,0.25), transparent); border-radius: 50%; transform: rotate(-30deg); }
        .cage-ball { position: absolute; border-radius: 50%; box-shadow: inset 0 -3px 6px rgba(0,0,0,0.3), inset 0 3px 6px rgba(255,255,255,0.3); }
        .cage.shaking { animation: shake 0.6s ease-in-out; }
        @keyframes shake { 0%,100% { transform: rotate(0); } 15% { transform: rotate(8deg) scale(1.02); } 30% { transform: rotate(-8deg) scale(1.02); } 45% { transform: rotate(6deg); } 60% { transform: rotate(-6deg); } 75% { transform: rotate(3deg); } 90% { transform: rotate(-3deg); } }
        .cage-ball:nth-child(1) { width:38px;height:38px;background:#2196F3;top:30%;left:20%;animation:fb1 2.5s infinite ease-in-out; }
        .cage-ball:nth-child(2) { width:35px;height:35px;background:#f44336;top:50%;left:55%;animation:fb2 3s infinite ease-in-out; }
        .cage-ball:nth-child(3) { width:36px;height:36px;background:#FF9800;top:25%;left:55%;animation:fb3 2.8s infinite ease-in-out; }
        .cage-ball:nth-child(4) { width:34px;height:34px;background:#4CAF50;top:55%;left:25%;animation:fb4 3.2s infinite ease-in-out; }
        .cage-ball:nth-child(5) { width:37px;height:37px;background:#FFEB3B;top:40%;left:38%;animation:fb5 2.6s infinite ease-in-out; }
        .cage-ball:nth-child(6) { width:33px;height:33px;background:#9C27B0;top:60%;left:45%;animation:fb1 3.5s infinite ease-in-out reverse; }
        @keyframes fb1 { 0%,100%{transform:translate(0,0)} 33%{transform:translate(15px,-20px)} 66%{transform:translate(-10px,15px)} }
        @keyframes fb2 { 0%,100%{transform:translate(0,0)} 33%{transform:translate(-20px,10px)} 66%{transform:translate(10px,-15px)} }
        @keyframes fb3 { 0%,100%{transform:translate(0,0)} 33%{transform:translate(10px,20px)} 66%{transform:translate(-15px,-10px)} }
        @keyframes fb4 { 0%,100%{transform:translate(0,0)} 33%{transform:translate(-10px,-15px)} 66%{transform:translate(20px,10px)} }
        @keyframes fb5 { 0%,100%{transform:translate(0,0)} 33%{transform:translate(15px,15px)} 66%{transform:translate(-15px,-20px)} }
        .chute { width: 60px; height: 40px; margin: -5px auto 0; background: linear-gradient(to bottom, #888, #555); border-radius: 0 0 10px 10px; position: relative; z-index: 2; box-shadow: 0 4px 8px rgba(0,0,0,0.4); }
        .display-area { margin: 15px 0; min-height: 150px; display: flex; flex-direction: column; align-items: center; justify-content: center; }
        .display-ball { width: 130px; height: 130px; border-radius: 50%; display: flex; flex-direction: column; align-items: center; justify-content: center; font-weight: bold; color: #333; position: relative; box-shadow: 0 10px 30px rgba(0,0,0,0.5), inset 0 -6px 12px rgba(0,0,0,0.2), inset 0 6px 12px rgba(255,255,255,0.4); opacity: 0; transform: scale(0); }
        .display-ball .ball-letter { font-size: 1.2rem; line-height: 1; }
        .display-ball .ball-number { font-size: 2.8rem; line-height: 1; }
        .display-ball::after { content: ''; position: absolute; top: 12%; left: 20%; width: 30%; height: 20%; background: radial-gradient(ellipse, rgba(255,255,255,0.6), transparent); border-radius: 50%; transform: rotate(-20deg); }
        .display-ball.reveal { animation: ballDrop 0.7s cubic-bezier(0.34, 1.56, 0.64, 1) forwards; }
        @keyframes ballDrop { 0% { opacity: 0; transform: scale(0) translateY(-80px) rotate(-180deg); } 50% { opacity: 1; transform: scale(1.15) translateY(10px) rotate(10deg); } 70% { transform: scale(0.95) translateY(-5px) rotate(-5deg); } 85% { transform: scale(1.05) translateY(3px) rotate(2deg); } 100% { opacity: 1; transform: scale(1) translateY(0) rotate(0deg); } }
        .display-placeholder { font-size: 3rem; color: #555; }
        .controls { margin: 10px 0 20px; }
        .btn { padding: 15px 30px; font-size: 1.4rem; border: none; border-radius: 12px; cursor: pointer; font-weight: bold; margin: 5px; transition: transform 0.1s; color: white; }
        .btn:active { transform: scale(0.95); }
        .btn-call { background: linear-gradient(135deg, #4caf50, #2e7d32); box-shadow: 0 4px 15px rgba(76,175,80,0.4); font-size: 1.5rem; }
        .btn-call:disabled { background: #666; box-shadow: none; cursor: not-allowed; }
        .btn-next { background: linear-gradient(135deg, #673ab7, #512da8); box-shadow: 0 4px 15px rgba(103,58,183,0.4); display: none; }
        .btn-reset { background: linear-gradient(135deg, #f44336, #c62828); font-size: 1rem; padding: 10px 20px; margin-top: 15px; }
        .players-column { flex: 1; min-width: 250px; max-width: 350px; }
        .players-list { background: rgba(255,255,255,0.08); padding: 15px; border-radius: 12px; backdrop-filter: blur(5px); border: 1px solid rgba(255,255,255,0.1); height: 100%; }
        .players-list h3 { margin-top: 0; color: #ffd700; text-align: center; font-size: 1.1rem; margin-bottom: 15px; }
        .players-list ul { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 8px; }
        .players-list li { padding: 10px; background: rgba(255,255,255,0.05); border-radius: 8px; display: flex; justify-content: space-between; font-size: 0.95rem; align-items: center; }
        .player-cards { background: rgba(255,215,0,0.2); padding: 2px 10px; border-radius: 12px; font-size: 0.8rem; color: #ffd700; font-weight: bold; }
        .board-column { flex: 1; min-width: 300px; max-width: 450px; }
        .board-column h3 { color: #ffd700; margin: 0 0 10px 0; font-size: 1.3rem; }
        .board-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 4px; }
        .board-col-header { font-size: 1.3rem; font-weight: bold; padding: 8px; border-radius: 8px 8px 0 0; }
        .board-col-header.hb { background: #1565C0; } .board-col-header.hi { background: #c62828; } .board-col-header.hn { background: #e65100; } .board-col-header.hg { background: #2e7d32; } .board-col-header.ho { background: #f9a825; color: #333; }
        .board-cell { width: 100%; aspect-ratio: 1; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 0.85rem; font-weight: bold; background: rgba(255,255,255,0.08); color: #666; transition: all 0.3s; border: 2px solid rgba(255,255,255,0.05); }
        .board-cell.called { color: white; transform: scale(1.1); box-shadow: 0 0 10px rgba(255,255,255,0.3); border-color: rgba(255,255,255,0.3); }
        .board-cell.called.cb { background: #2196F3; } .board-cell.called.ci { background: #f44336; } .board-cell.called.cn { background: #FF9800; } .board-cell.called.cg { background: #4CAF50; } .board-cell.called.co { background: #FFEB3B; color: #333; }
        .winner-alert { color: #ffd700; font-size: 2rem; font-weight: bold; animation: pulse 1s infinite; text-shadow: 0 0 20px rgba(255,215,0,0.5); margin: 10px 0; }
        @keyframes pulse { 0%,100%{transform:scale(1)} 50%{transform:scale(1.08)} }
        @media (max-width: 900px) { .stage { flex-direction: column; align-items: center; } .players-column, .board-column { width: 100%; max-width: 400px; } }
        .sound-btn { background: #333; color: white; border: 1px solid #555; padding: 8px 15px; border-radius: 20px; cursor: pointer; font-size: 0.9rem; margin: 10px; }
    </style>
</head>
<body>
    <h1>🎱 BINGO CALLER 🎱</h1>
    <button class="sound-btn" onclick="enableSound()">🔊 Enable Sound Effects</button>
    <div class="pot-container">
        <div class="pot-display">
            <div class="pot-label">Current Pot</div>
            <div class="pot-amount" id="pot-amount">$0</div>
        </div>
    </div>
    <div class="mode-container">
        <button class="mode-btn active" id="mode-1" onclick="setMode(1)">Standard ($1/card)</button>
        <button class="mode-btn blackout-2" id="mode-2" onclick="setMode(2)">Blackout ($2/card)</button>
        <button class="mode-btn blackout-5" id="mode-5" onclick="setMode(5)">Blackout ($5/card)</button>
    </div>
    <div class="pattern-section">
        <div class="pattern-title">🎯 TARGET PATTERN</div>
        <div class="pattern-container">
            <button class="pattern-btn active" id="pat-straight" onclick="setPattern('straight')">Straight</button>
            <button class="pattern-btn" id="pat-4sides" onclick="setPattern('4sides')">4 Sides</button>
            <button class="pattern-btn" id="pat-parallel" onclick="setPattern('parallel')">Parallel</button>
            <button class="pattern-btn" id="pat-cross" onclick="setPattern('cross')">Cross (X)</button>
            <button class="pattern-btn blackout-btn" id="pat-blackout" onclick="setPattern('blackout')">BLACKOUT</button>
            <div class="pattern-preview" id="pattern-preview"></div>
        </div>
    </div>
    <div id="winner-msg" class="winner-alert" style="display:none;"></div>
    <div class="stage">
        <div class="machine-column">
            <div class="cage-wrapper">
                <div class="cage" id="cage">
                    <div class="cage-ball"></div><div class="cage-ball"></div><div class="cage-ball"></div>
                    <div class="cage-ball"></div><div class="cage-ball"></div><div class="cage-ball"></div>
                </div>
            </div>
            <div class="chute"></div>
            <div class="display-area">
                <div id="display-ball" class="display-ball">
                    <span class="ball-letter" id="ball-letter"></span>
                    <span class="ball-number" id="ball-number"></span>
                </div>
                <div id="display-placeholder" class="display-placeholder">🎱</div>
            </div>
            <div class="controls">
                <button class="btn btn-call" id="call-btn" onclick="callNumber()">🎤 Call Next Number</button>
                <br>
                <button class="btn btn-next" id="next-round-btn" onclick="nextRound()"> NEXT ROUND</button>
                <br>
                <button class="btn btn-reset" onclick="resetGame()">Full Reset</button>
            </div>
        </div>
        <div class="players-column">
            <div class="players-list">
                <h3> Players in Game (<span id="player-count">0</span>)</h3>
                <ul id="players-list">
                    <li style="text-align:center; color:#888; display:block;">Waiting for players...</li>
                </ul>
            </div>
        </div>
        <div class="board-column">
            <h3>📋 Called Numbers</h3>
            <div class="board-grid" id="board-grid"></div>
        </div>
    </div>
    <script>
        let soundEnabled = false;
        const popSound = new Audio('https://actions.google.com/sounds/v1/cartoon/pop.ogg');
        const winSound = new Audio('https://actions.google.com/sounds/v1/crowds/female_cheer.ogg');
        
        function enableSound() {
            soundEnabled = true;
            popSound.play().then(() => popSound.pause()).catch(() => {});
            document.querySelector('.sound-btn').innerText = '🔊 Sound Enabled!';
        }
        function playPop() { if(soundEnabled) { popSound.currentTime = 0; popSound.play(); } }
        function playWin() { if(soundEnabled) { winSound.currentTime = 0; winSound.play(); } }
        const ballColors = { B:'#2196F3', I:'#f44336', N:'#FF9800', G:'#4CAF50', O:'#FFEB3B' };
        const ballTextDark = { O: true };
        function getLetter(n) { if(n<=15)return'B';if(n<=30)return'I';if(n<=45)return'N';if(n<=60)return'G';return'O'; }
        function getColorClass(n) { if(n<=15)return'cb';if(n<=30)return'ci';if(n<=45)return'cn';if(n<=60)return'cg';return'co'; }
        function buildBoard() {
            const grid = document.getElementById('board-grid');
            const headers = [['B','hb'],['I','hi'],['N','hn'],['G','hg'],['O','ho']];
            headers.forEach(([l,c]) => { grid.innerHTML += `<div class="board-col-header ${c}">${l}</div>`; });
            for (let row = 0; row < 15; row++) {
                for (let col = 0; col < 5; col++) {
                    const num = col * 15 + row + 1;
                    grid.innerHTML += `<div class="board-cell" id="bc-${num}">${num}</div>`;
                }
            }
        }
        buildBoard();
        function updateBoard(calledNums) {
            document.querySelectorAll('.board-cell.called').forEach(el => { el.classList.remove('called','cb','ci','cn','cg','co'); });
            calledNums.forEach(n => {
                const cell = document.getElementById(`bc-${n}`);
                if (cell) { cell.classList.add('called', getColorClass(n)); }
            });
        }
        let isCalling = false;
        function callNumber() {
            if (isCalling) return;
            isCalling = true;
            const btn = document.getElementById('call-btn');
            btn.disabled = true;
            const cage = document.getElementById('cage');
            cage.classList.add('shaking');
            setTimeout(() => {
                cage.classList.remove('shaking');
                fetch('/api/call', { method: 'POST' })
                    .then(r => r.json())
                    .then(data => {
                        if (data.number) {
                            const letter = getLetter(data.number);
                            const color = ballColors[letter];
                            const ball = document.getElementById('display-ball');
                            const placeholder = document.getElementById('display-placeholder');
                            placeholder.style.display = 'none';
                            ball.style.background = `radial-gradient(circle at 35% 35%, ${color}, ${color}dd)`;
                            ball.style.color = ballTextDark[letter] ? '#333' : '#fff';
                            document.getElementById('ball-letter').innerText = letter;
                            document.getElementById('ball-number').innerText = data.number;
                            ball.classList.remove('reveal');
                            void ball.offsetWidth;
                            ball.classList.add('reveal');
                            updateBoard(data.all_called);
                            playPop();
                        } else { alert("All numbers have been called!"); }
                        isCalling = false;
                        btn.disabled = false;
                    });
            }, 700);
        }
        function nextRound() {
            fetch('/api/next_round', { method: 'POST' }).then(() => {
                document.getElementById('winner-msg').style.display = 'none';
                document.getElementById('next-round-btn').style.display = 'none';
                document.getElementById('call-btn').disabled = false;
                const ball = document.getElementById('display-ball');
                ball.classList.remove('reveal');
                ball.style.opacity = '0';
                ball.style.transform = 'scale(0)';
                document.getElementById('display-placeholder').style.display = 'block';
                updateBoard([]);
            });
        }
        function resetGame() {
            if (confirm("Full reset? All cards, players, and marks will be cleared.")) {
                fetch('/api/reset', { method: 'POST' }).then(() => location.reload());
            }
        }
        function setMode(price) {
            fetch(`/api/set_price/${price}`, { method: 'POST' })
                .then(r => r.json())
                .then(data => {
                    if (data.success) {
                        document.querySelectorAll('.mode-btn').forEach(btn => btn.classList.remove('active'));
                        document.getElementById(`mode-${price}`).classList.add('active');
                        document.getElementById('pot-amount').innerText = `$${data.new_pot}`;
                    }
                });
        }
        function setPattern(pattern) {
            fetch(`/api/set_pattern/${pattern}`, { method: 'POST' })
                .then(r => r.json())
                .then(data => {
                    if (data.success) {
                        document.querySelectorAll('.pattern-btn').forEach(btn => btn.classList.remove('active'));
                        document.getElementById(`pat-${pattern}`).classList.add('active');
                        renderPatternPreview(pattern);
                    }
                });
        }
        function renderPatternPreview(pattern) {
            const grid = document.getElementById('pattern-preview');
            grid.innerHTML = '';
            const activeCells = [];
            if (pattern === 'straight') {
                for(let i=0; i<5; i++) activeCells.push([2, i], [i, 2], [i, i], [i, 4-i]);
            } else if (pattern === '4sides') {
                for(let i=0; i<5; i++) activeCells.push([0, i], [4, i], [i, 0], [i, 4]);
            } else if (pattern === 'parallel') {
                for(let i=0; i<5; i++) activeCells.push([0, i], [1, i], [i, 0], [i, 1]);
            } else if (pattern === 'cross') {
                for(let i=0; i<5; i++) activeCells.push([i, i], [i, 4-i]);
            } else if (pattern === 'blackout') {
                for(let r=0; r<5; r++) {
                    for(let c=0; c<5; c++) {
                        activeCells.push([r, c]);
                    }
                }
            }
            for(let r=0; r<5; r++) {
                for(let c=0; c<5; c++) {
                    const cell = document.createElement('div');
                    cell.className = 'p-cell';
                    if (r===2 && c===2) cell.classList.add('free');
                    else if (activeCells.some(([ar, ac]) => ar===r && ac===c)) cell.classList.add('active');
                    grid.appendChild(cell);
                }
            }
        }
        function updatePlayers() {
            fetch('/api/get_players?t=' + Date.now()).then(r => r.json()).then(data => {
                const list = document.getElementById('players-list');
                const countSpan = document.getElementById('player-count');
                if (!data.players || data.players.length === 0) {
                    countSpan.innerText = '0';
                    list.innerHTML = '<li style="text-align:center; color:#888; display:block;">Waiting for players...</li>';
                } else {
                    countSpan.innerText = data.players.length;
                    list.innerHTML = data.players.map(p => `
                        <li>
                            <span><strong>${p.name}</strong> <span style="color:#888; font-size:0.75rem;">(${p.id})</span></span>
                            <span class="player-cards">${p.card_count} card${p.card_count !== 1 ? 's' : ''}</span>
                        </li>
                    `).join('');
                }
                if (data.total_pot !== undefined) document.getElementById('pot-amount').innerText = `$${data.total_pot}`;
            }).catch(err => console.error('Error fetching players:', err));
        }
        setInterval(() => {
            fetch('/api/check_winner').then(r => r.json()).then(data => {
                if (data.winner) {
                    document.getElementById('winner-msg').innerText = `🎉 ${data.winner_name} WON $${data.total_pot}! 🎉`;
                    document.getElementById('winner-msg').style.display = 'block';
                    playWin();
                    document.getElementById('next-round-btn').style.display = 'inline-block';
                    document.getElementById('call-btn').disabled = true;
                }
                if (data.total_pot !== undefined) document.getElementById('pot-amount').innerText = `$${data.total_pot}`;
            });
            updatePlayers();
        }, 2000);
        renderPatternPreview('straight');
        updatePlayers();
    </script>
</body>
</html>
"""

PLAYER_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>My Bingo Cards</title>
    <style>
        * { box-sizing: border-box; }
        body { font-family: 'Segoe UI', sans-serif; background: linear-gradient(135deg, #0d47a1, #1565c0); color: white; margin: 0; padding: 15px; display: flex; flex-direction: column; align-items: center; min-height: 100vh; }
        h2 { margin: 5px 0; font-size: 1.1rem; opacity: 0.8; }
        .player-pot { background: linear-gradient(135deg, #ffd700, #ff8c00); color: #1a1a2e; padding: 8px 20px; border-radius: 20px; font-weight: 900; font-size: 1.2rem; margin: 10px 0; box-shadow: 0 4px 15px rgba(255, 215, 0, 0.3); border: 2px solid #fff; }
        .target-pattern { background: rgba(156,39,176,0.2); border: 2px solid #9c27b0; color: #e1bee7; padding: 8px 20px; border-radius: 20px; font-weight: bold; font-size: 1rem; margin-bottom: 10px; text-align: center; }
        .called-ball-area { margin: 10px 0 15px; display: flex; flex-direction: column; align-items: center; min-height: 90px; }
        .called-ball-label { font-size: 0.9rem; opacity: 0.7; margin-bottom: 5px; }
        .called-ball { width: 75px; height: 75px; border-radius: 50%; display: flex; flex-direction: column; align-items: center; justify-content: center; font-weight: bold; color: white; box-shadow: 0 6px 15px rgba(0,0,0,0.4), inset 0 -4px 8px rgba(0,0,0,0.2), inset 0 4px 8px rgba(255,255,255,0.3); position: relative; transition: all 0.3s; }
        .called-ball .cb-letter { font-size: 0.8rem; line-height: 1; }
        .called-ball .cb-number { font-size: 1.6rem; line-height: 1; }
        .called-ball::after { content: ''; position: absolute; top: 10%; left: 18%; width: 30%; height: 18%; background: radial-gradient(ellipse, rgba(255,255,255,0.5), transparent); border-radius: 50%; transform: rotate(-20deg); }
        .called-ball.pop { animation: ballPop 0.5s cubic-bezier(0.34, 1.56, 0.64, 1); }
        @keyframes ballPop { 0%{transform:scale(0.5) rotate(-90deg)} 60%{transform:scale(1.15) rotate(5deg)} 100%{transform:scale(1) rotate(0)} }
        .called-ball-empty { width: 75px; height: 75px; border-radius: 50%; border: 3px dashed rgba(255,255,255,0.3); display: flex; align-items: center; justify-content: center; font-size: 1.5rem; }
        .name-input { margin-bottom: 10px; width: 100%; max-width: 400px; display: flex; align-items: center; gap: 10px; }
        .name-input label { font-weight: bold; font-size: 1rem; white-space: nowrap; }
        .name-input input { flex: 1; padding: 8px; font-size: 1rem; border: none; border-radius: 6px; background: rgba(255,255,255,0.15); color: white; border-bottom: 2px solid rgba(255,255,255,0.5); text-align: center; }
        .name-input input::placeholder { color: rgba(255,255,255,0.5); }
        .add-btn { background: linear-gradient(135deg, #ff9800, #f57c00); color: white; border: none; padding: 12px 24px; font-size: 1.1rem; border-radius: 10px; margin-bottom: 15px; font-weight: bold; width: 100%; max-width: 400px; box-shadow: 0 4px 10px rgba(0,0,0,0.2); }
        .add-btn:active { transform: scale(0.97); }
        .card-wrapper { margin-bottom: 25px; width: 100%; max-width: 400px; }
        .card-wrapper h3 { display: flex; justify-content: space-between; align-items: center; margin: 0; background: #0a3470; padding: 10px 15px; border-radius: 10px 10px 0 0; font-size: 1.1rem; }
        .remove-btn { background: #f44336; color: white; border: none; padding: 4px 10px; border-radius: 6px; font-size: 0.85rem; cursor: pointer; font-weight: bold; }
        .remove-btn:active { background: #d32f2f; }
        .grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 5px; background: #0a3470; padding: 10px; border-radius: 0 0 10px 10px; }
        .header { font-size: 1.1rem; font-weight: bold; text-align: center; padding: 6px; background: #1565c0; border-radius: 6px; }
        .cell { background: white; color: #333; font-size: 1.3rem; font-weight: bold; border-radius: 8px; display: flex; align-items: center; justify-content: center; cursor: pointer; user-select: none; aspect-ratio: 1/1; transition: 0.15s; border: 2px solid transparent; }
        .cell:active { transform: scale(0.9); }
        .cell.marked { background: #4caf50; color: white; border-color: #2e7d32; box-shadow: 0 0 8px rgba(76,175,80,0.5); }
        .cell.free { background: #ff9800; color: white; }
        .cell.shake { animation: shakeInvalid 0.4s ease-in-out; background: #ffcdd2; border-color: #f44336; }
        @keyframes shakeInvalid { 0%, 100% { transform: translateX(0); } 25% { transform: translateX(-6px); } 75% { transform: translateX(6px); } }
        .bingo-btn { margin-top: 15px; padding: 18px; font-size: 1.8rem; background: linear-gradient(135deg, #d32f2f, #b71c1c); color: white; border: none; border-radius: 12px; width: 100%; max-width: 400px; font-weight: bold; position: sticky; bottom: 15px; box-shadow: 0 6px 20px rgba(0,0,0,0.4); z-index: 10; }
        .bingo-btn:active { transform: scale(0.97); }
        .status { margin-top: 10px; font-size: 1.1rem; min-height: 30px; text-align: center; transition: color 0.3s; }
        .modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.85); z-index: 100; justify-content: center; align-items: center; }
        .modal.show { display: flex; animation: fadeIn 0.3s; }
        @keyframes fadeIn { from{opacity:0} to{opacity:1} }
        .modal-content { background: white; color: #333; padding: 30px; border-radius: 16px; text-align: center; max-width: 320px; width: 90%; box-shadow: 0 10px 30px rgba(0,0,0,0.5); }
        .modal-content h2 { color: #d32f2f; margin-top: 0; font-size: 1.6rem; }
        .modal-content p { font-size: 1.1rem; margin: 15px 0; }
        .modal-pot { font-size: 2.5rem; font-weight: 900; color: #ff8c00; margin: 10px 0; text-shadow: 1px 1px 2px rgba(0,0,0,0.1); }
        .modal-btn { background: linear-gradient(135deg, #4caf50, #388e3c); color: white; border: none; padding: 15px 30px; font-size: 1.3rem; border-radius: 10px; margin-top: 10px; cursor: pointer; font-weight: bold; width: 100%; box-shadow: 0 4px 10px rgba(0,0,0,0.2); }
        .modal-btn:active { transform: scale(0.97); }
        .sound-btn { background: #2196F3; color: white; border: none; padding: 8px 15px; border-radius: 20px; cursor: pointer; font-size: 0.9rem; margin: 10px auto; display: block; }
    </style>
</head>
<body>
    <h2>Session: {{ session_id[:6] }}</h2>
    <button class="sound-btn" onclick="enableSound()">🔊 Enable Sound Effects</button>
    <div class="player-pot">Prize Pot: $<span id="player-pot-amount">0</span></div>
    <div class="target-pattern" id="target-pattern-display">🎯 Target: STRAIGHT (Line)</div>
    <div class="called-ball-area">
        <div class="called-ball-label">Last Called</div>
        <div id="called-ball-container">
            <div class="called-ball-empty">🎱</div>
        </div>
    </div>
    <div class="name-input">
        <label>Name:</label>
        <input type="text" id="player-name" value="{{ player_name }}" placeholder="Enter your name" maxlength="15" onchange="updateName(this.value)">
    </div>
    <button class="add-btn" id="add-card-btn" onclick="addCard()" {% if game_started %}style="display:none;"{% endif %}>+ Add Another Card (${{ price_per_card }})</button>
    <div id="cards-container"></div>
    <button class="bingo-btn" onclick="claimBingo()">BINGO!</button>
    <div class="status" id="status"></div>
    <div id="game-over-modal" class="modal">
        <div class="modal-content">
            <h2>🎉 <span id="modal-winner-name"></span> got BINGO! 🎉</h2>
            <p>You won:</p>
            <div class="modal-pot" id="modal-pot-amount">$0</div>
            <button class="modal-btn" onclick="playAgain()">Play Again</button>
        </div>
    </div>
    <script>
        let soundEnabled = false;
        const popSound = new Audio('https://actions.google.com/sounds/v1/cartoon/pop.ogg');
        const winSound = new Audio('https://actions.google.com/sounds/v1/crowds/female_cheer.ogg');
        
        function enableSound() {
            soundEnabled = true;
            popSound.play().then(() => popSound.pause()).catch(() => {});
            document.querySelector('.sound-btn').innerText = ' Sound Enabled!';
        }
        function playPop() { if(soundEnabled) { popSound.currentTime = 0; popSound.play(); } }
        function playWin() { if(soundEnabled) { winSound.currentTime = 0; winSound.play(); } }
        const sessionId = "{{ session_id }}";
        const initialCards = {{ cards | tojson }};
        const container = document.getElementById('cards-container');
        let isModalShowing = false;
        let lastCalledNum = 0;
        let calledNumbers = new Set();
        let currentPrice = {{ price_per_card }};
        let currentPattern = '{{ current_pattern }}';
        const ballColors = { B:'#2196F3', I:'#f44336', N:'#FF9800', G:'#4CAF50', O:'#FFEB3B' };
        const ballTextDark = { O: true };
        const patternNames = { 'straight': 'STRAIGHT (Line)', '4sides': '4 SIDES (Frame)', 'parallel': 'PARALLEL (2 Lines)', 'cross': 'CROSS (X)', 'blackout': 'BLACKOUT (Full Card)' };
        function getLetter(n) { if(n<=15)return'B';if(n<=30)return'I';if(n<=45)return'N';if(n<=60)return'G';return'O'; }
        function createCardHTML(cardId, cardData, index) {
            let html = `<div class="card-wrapper" data-card-id="${cardId}">
                <h3><span>Card ${index}</span><button class="remove-btn" onclick="removeCard('${cardId}', this.closest('.card-wrapper'))">X</button></h3>
                <div class="grid">
                    <div class="header">B</div><div class="header">I</div><div class="header">N</div><div class="header">G</div><div class="header">O</div>`;
            for (let r = 0; r < 5; r++) {
                for (let c = 0; c < 5; c++) {
                    let num = cardData[r][c];
                    if (num === 0) html += `<div class="cell free marked" data-num="0">FREE</div>`;
                    else html += `<div class="cell" data-num="${num}" onclick="toggleMark(this)">${num}</div>`;
                }
            }
            html += `</div></div>`;
            return html;
        }
        initialCards.forEach((item, index) => { container.innerHTML += createCardHTML(item[0], item[1], index + 1); });
        function toggleMark(el) {
            const num = parseInt(el.dataset.num);
            if (num === 0) return;
            if (!calledNumbers.has(num)) {
                el.classList.remove('shake'); void el.offsetWidth; el.classList.add('shake');
                const status = document.getElementById('status');
                status.innerText = `⚠️ ${num} hasn't been called yet!`; status.style.color = '#ffcdd2';
                setTimeout(() => { el.classList.remove('shake'); if (status.innerText.includes(num)) status.innerText = ''; }, 1500);
                return;
            }
            el.classList.toggle('marked');
        }
        function addCard() {
            fetch(`/api/add_card/${sessionId}`, { method: 'POST' })
                .then(r => r.json())
                .then(data => {
                    if (!data.success) {
                        alert(data.message);
                        return;
                    }
                    const count = container.children.length + 1;
                    container.innerHTML += createCardHTML(data.card_id, data.card, count);
                    window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
                })
                .catch(err => {
                    console.error('Error adding card:', err);
                    alert('Failed to add card. Please try again.');
                });
        }
        function removeCard(cardId, element) {
            if (container.children.length <= 1) { alert("You must keep at least one card!"); return; }
            if (confirm("Remove this card?")) {
                fetch(`/api/remove_card/${sessionId}/${cardId}`, { method: 'POST' })
                    .then(r => r.json())
                    .then(data => {
                        if (data.success) {
                            element.remove();
                            document.querySelectorAll('.card-wrapper').forEach((w, i) => { w.querySelector('h3 span').innerText = `Card ${i + 1}`; });
                        }
                    });
            }
        }
        function updateName(name) {
            fetch(`/api/update_name/${sessionId}`, { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ name }) });
        }
        function updateCalledBall(num) {
            if (num && num !== lastCalledNum) {
                lastCalledNum = num;
                const letter = getLetter(num); const color = ballColors[letter]; const dark = ballTextDark[letter];
                const c = document.getElementById('called-ball-container');
                c.innerHTML = `<div class="called-ball pop" style="background:radial-gradient(circle at 35% 35%, ${color}, ${color}dd); color:${dark?'#333':'#fff'}">
                    <span class="cb-letter">${letter}</span><span class="cb-number">${num}</span></div>`;
                    playPop();
            } else if (!num && lastCalledNum !== 0) {
                lastCalledNum = 0;
                document.getElementById('called-ball-container').innerHTML = '<div class="called-ball-empty">🎱</div>';
            }
        }
        function showGameOverModal(winnerName, pot) {
            document.getElementById('modal-winner-name').innerText = winnerName;
            document.getElementById('modal-pot-amount').innerText = `$${pot}`;
            document.getElementById('game-over-modal').classList.add('show');
            isModalShowing = true;
            playWin();
        }
        function hideModalAndClearMarks() {
            document.getElementById('game-over-modal').classList.remove('show');
            document.querySelectorAll('.cell.marked').forEach(cell => { if (cell.dataset.num !== '0') cell.classList.remove('marked'); });
            document.getElementById('status').innerText = '';
            isModalShowing = false;
        }
        function playAgain() {
            fetch(`/api/clear_marks/${sessionId}`, { method: 'POST' }).then(() => hideModalAndClearMarks());
        }
        function claimBingo() {
            const wrappers = document.querySelectorAll('.card-wrapper');
            const markedCards = {};
            wrappers.forEach(w => {
                const cardId = w.dataset.cardId;
                markedCards[cardId] = Array.from(w.querySelectorAll('.cell.marked')).map(el => parseInt(el.dataset.num));
            });
            fetch('/api/claim_bingo', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ session_id: sessionId, marked_cards: markedCards })
            }).then(r => r.json()).then(data => {
                const status = document.getElementById('status');
                if (data.win) {
                    status.innerText = `🎉 BINGO! YOU WON $${data.pot} on Card ${data.winning_card_index}! 🎉`;
                    status.style.color = "#ffeb3b"; status.style.fontSize = "1.4rem";
                } else if (data.message) {
                    status.innerText = data.message; status.style.color = "#ffcdd2"; status.style.fontSize = "1.1rem";
                } else {
                    status.innerText = "Not quite yet... keep playing!"; status.style.color = "#ffcdd2"; status.style.fontSize = "1.1rem";
                }
            });
        }
        setInterval(() => {
            fetch(`/api/heartbeat/${sessionId}`, { method: 'POST' });
        }, 5000);
        setInterval(() => {
            fetch('/api/check_winner').then(r => r.json()).then(data => {
                if (data.winner && !isModalShowing) showGameOverModal(data.winner_name, data.total_pot);
                else if (!data.winner && isModalShowing) hideModalAndClearMarks();
                if (data.last_called !== undefined) updateCalledBall(data.last_called);
                if (data.called_numbers) calledNumbers = new Set(data.called_numbers);
                if (data.total_pot !== undefined) document.getElementById('player-pot-amount').innerText = data.total_pot;
                if (data.price_per_card !== undefined && currentPrice !== data.price_per_card) {
                    currentPrice = data.price_per_card;
                    const btn = document.getElementById('add-card-btn');
                    if (btn) btn.innerText = `+ Add Another Card ($${currentPrice})`;
                }
                if (data.current_pattern !== undefined && data.current_pattern !== currentPattern) {
                    currentPattern = data.current_pattern;
                    document.getElementById('target-pattern-display').innerText = `🎯 Target: ${patternNames[currentPattern]}`;
                }
                const btn = document.getElementById('add-card-btn');
                if (btn) {
                    if (data.game_started) {
                        btn.style.display = 'none';
                    } else {
                        btn.style.display = 'block';
                    }
                }
            });
        }, 2000);
    </script>
</body>
</html>
"""

@app.route('/')
def landing():
    return render_template_string("""
<!DOCTYPE html>
<html>
<head>
    <title>Family Bingo</title>
    <style>
        body { font-family: sans-serif; background: #1a1a2e; color: white; text-align: center; padding: 50px; }
        h1 { color: #ffd700; }
        .box { background: rgba(255,255,255,0.1); padding: 30px; border-radius: 10px; margin: 20px auto; max-width: 400px; }
        .link { background: #2196F3; padding: 15px; border-radius: 5px; margin: 10px 0; word-break: break-all; font-size: 0.9rem; }
        .host { background: #4caf50; }
        a { color: white; text-decoration: none; }
    </style>
</head>
<body>
    <h1>🎱 Family Bingo</h1>
    <div class="box">
        <h3>Host Link (You):</h3>
        <div class="link host"><a href="/host">""" + request.host_url + """host</a></div>
    </div>
    <div class="box">
        <h3>Player Link (Share this):</h3>
        <div class="link"><a href="/join">""" + request.host_url + """join</a></div>
    </div>
</body>
</html>
    """)

@app.route('/host')
def host():
    return render_template_string(HOST_HTML, called_numbers=game_state['called_numbers'])

@app.route('/join')
def join_page():
    session_id = str(uuid.uuid4())
    game_state['sessions'][session_id] = []
    game_state['session_names'][session_id] = f"Player {session_id[:6]}"
    game_state['last_seen'][session_id] = time.time()
    new_card_id = str(uuid.uuid4())
    game_state['cards'][new_card_id] = generate_card()
    game_state['marked'][new_card_id] = set()
    game_state['sessions'][session_id].append(new_card_id)
    return redirect(f'/play/{session_id}')

@app.route('/play/<session_id>')
def player(session_id):
    if session_id not in game_state['sessions']:
        game_state['sessions'][session_id] = []
        game_state['session_names'][session_id] = f"Player {session_id[:6]}"
        game_state['last_seen'][session_id] = time.time()
        new_card_id = str(uuid.uuid4())
        game_state['cards'][new_card_id] = generate_card()
        game_state['marked'][new_card_id] = set()
        game_state['sessions'][session_id].append(new_card_id)
    else:
        game_state['last_seen'][session_id] = time.time()
    session_cards = [(cid, game_state['cards'][cid]) for cid in game_state['sessions'][session_id]]
    player_name = game_state['session_names'][session_id]
    game_started = len(game_state['called_numbers']) > 0
    return render_template_string(PLAYER_HTML, session_id=session_id, cards=session_cards, player_name=player_name, game_started=game_started, price_per_card=game_state['price_per_card'], current_pattern=game_state['current_pattern'])

@app.route('/api/heartbeat/<session_id>', methods=['POST'])
def heartbeat(session_id):
    if session_id in game_state['sessions']:
        game_state['last_seen'][session_id] = time.time()
    return jsonify({'success': True})

@app.route('/api/add_card/<session_id>', methods=['POST'])
def add_card(session_id):
    if len(game_state['called_numbers']) > 0:
        return jsonify({'success': False, 'message': 'Game already started! No new cards allowed.'})
    if session_id not in game_state['sessions']:
        game_state['sessions'][session_id] = []
        game_state['session_names'][session_id] = f"Player {session_id[:6]}"
    new_card_id = str(uuid.uuid4())
    game_state['cards'][new_card_id] = generate_card()
    game_state['marked'][new_card_id] = set()
    game_state['sessions'][session_id].append(new_card_id)
    game_state['last_seen'][session_id] = time.time()
    return jsonify({'success': True, 'card_id': new_card_id, 'card': game_state['cards'][new_card_id]})

@app.route('/api/remove_card/<session_id>/<card_id>', methods=['POST'])
def remove_card(session_id, card_id):
    if session_id in game_state['sessions'] and card_id in game_state['sessions'][session_id]:
        game_state['sessions'][session_id].remove(card_id)
        if card_id in game_state['cards']: del game_state['cards'][card_id]
        if card_id in game_state['marked']: del game_state['marked'][card_id]
        return jsonify({'success': True})
    return jsonify({'success': False})

@app.route('/api/update_name/<session_id>', methods=['POST'])
def update_name(session_id):
    data = request.json
    name = data.get('name', '').strip()
    if name and session_id in game_state['sessions']:
        game_state['session_names'][session_id] = name
    return jsonify({'success': True})

@app.route('/api/set_price/<int:price>', methods=['POST'])
def set_price(price):
    if price in [1, 2, 5]:
        game_state['price_per_card'] = price
        return jsonify({'success': True, 'new_pot': get_total_pot()})
    return jsonify({'success': False})

@app.route('/api/set_pattern/<pattern>', methods=['POST'])
def set_pattern(pattern):
    if pattern in ['straight', '4sides', 'parallel', 'cross', 'blackout']:
        game_state['current_pattern'] = pattern
        return jsonify({'success': True})
    return jsonify({'success': False})

@app.route('/api/get_players')
def get_players():
    cleanup_dead_sessions()
    players = []
    for sid, cards in game_state['sessions'].items():
        name = game_state['session_names'].get(sid, f"Player {sid[:6]}")
        players.append({'id': sid[:6], 'name': name, 'card_count': len(cards)})
    return jsonify({'players': players, 'total_pot': get_total_pot(), 'price_per_card': game_state['price_per_card'], 'current_pattern': game_state['current_pattern']})

@app.route('/api/call', methods=['POST'])
def call_number():
    if game_state['remaining_numbers']:
        num = random.choice(game_state['remaining_numbers'])
        game_state['remaining_numbers'].remove(num)
        game_state['called_numbers'].append(num)
        return jsonify({'number': num, 'letter': get_ball_letter(num), 'all_called': sorted(game_state['called_numbers'])})
    return jsonify({'number': None})

@app.route('/api/claim_bingo', methods=['POST'])
def claim_bingo():
    if game_state['game_over']:
        return jsonify({'win': False, 'message': 'Game is over! Wait for next round.'})
    data = request.json
    session_id = data['session_id']
    marked_cards = data['marked_cards']
    if session_id in game_state['sessions']:
        for index, card_id in enumerate(game_state['sessions'][session_id]):
            if card_id in marked_cards:
                marked_nums = set(marked_cards[card_id])
                valid_marks = marked_nums.issubset(set(game_state['called_numbers']) | {0})
                if not valid_marks:
                    return jsonify({'win': False, 'message': '️ You marked a number that hasn\'t been called yet!'})
                game_state['marked'][card_id] = marked_nums
                if check_bingo(marked_nums, game_state['cards'][card_id]):
                    game_state['winner'] = session_id
                    game_state['game_over'] = True
                    return jsonify({'win': True, 'winning_card_index': index + 1, 'pot': get_total_pot()})
    return jsonify({'win': False})

@app.route('/api/check_winner')
def check_winner():
    cleanup_dead_sessions()
    winner_name = "Unknown"
    if game_state['winner']:
        winner_name = game_state['session_names'].get(game_state['winner'], "Player")
    last_called = game_state['called_numbers'][-1] if game_state['called_numbers'] else 0
    return jsonify({
        'winner': game_state['winner'] is not None,
        'winner_name': winner_name,
        'last_called': last_called,
        'called_numbers': game_state['called_numbers'],
        'total_pot': get_total_pot(),
        'price_per_card': game_state['price_per_card'],
        'current_pattern': game_state['current_pattern'],
        'game_started': len(game_state['called_numbers']) > 0
    })

@app.route('/api/next_round', methods=['POST'])
def next_round():
    game_state['called_numbers'].clear()
    game_state['remaining_numbers'] = list(range(1, 76))
    for card_id in game_state['marked']:
        game_state['marked'][card_id] = set()
    game_state['winner'] = None
    game_state['game_over'] = False
    return jsonify({'status': 'next_round'})

@app.route('/api/clear_marks/<session_id>', methods=['POST'])
def clear_marks(session_id):
    if session_id in game_state['sessions']:
        for card_id in game_state['sessions'][session_id]:
            if card_id in game_state['marked']:
                game_state['marked'][card_id] = set()
    return jsonify({'success': True})

@app.route('/api/reset', methods=['POST'])
def reset_game():
    game_state['called_numbers'].clear()
    game_state['remaining_numbers'] = list(range(1, 76))
    game_state['cards'].clear()
    game_state['marked'].clear()
    game_state['sessions'].clear()
    game_state['session_names'].clear()
    game_state['last_seen'].clear()
    game_state['winner'] = None
    game_state['game_over'] = False
    game_state['price_per_card'] = 1
    game_state['current_pattern'] = 'straight'
    return jsonify({'status': 'reset'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"\n--- FAMILY BINGO STARTED ON PORT {port} ---")
    app.run(host='0.0.0.0', port=port, debug=False)
