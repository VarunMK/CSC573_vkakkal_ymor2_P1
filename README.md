# P2P-CI System Implementation

A simple peer-to-peer system with centralized index for downloading RFCs.

## Components

- `server.py` - Centralized index server (port 7734)
- `peer.py` - P2P peer client with upload/download capabilities

## Usage

### Start Server
```bash
python3 server.py
```

### Start Peer
Each peer maintains its own RFC directory and a unique hostname identifier. Use
`--rfc-dir` to point the peer at its personal folder (an empty folder is fine for
download-only peers), and optionally `--peer-name` to override the advertised
hostname (defaults to `<actual-host>-<pid>`):
```bash
python3 peer.py [server_host] --rfc-dir peer1_rfcs --peer-name peer1.csc.ncsu.edu
```
If you omit `--rfc-dir`, the peer defaults to a directory named
`rfcs_<hostname>-<pid>` and creates it if needed.

### Peer Commands
- `add <rfc_num> <title>` - Add RFC to index
- `lookup <rfc_num>` - Find peers with RFC  
- `list` - List all RFCs
- `download <rfc_num>` - Download RFC from peer
- `quit` - Exit

## Protocol Support

- **P2S Protocol**: ADD, LOOKUP, LIST operations between peer and server
- **P2P Protocol**: GET operation for RFC downloads between peers
- **Concurrent**: Server handles multiple peers simultaneously
- **RFC Storage**: Each peer stores RFCs in its own directory as `rfc<num>.txt`

## Example workflow

1. Generate sample RFC folders (optional, creates one RFC per directory):
   ```bash
   python3 test_rfc.py peer1_rfcs peer2_rfcs peer3_rfcs
   ```
2. Start server: `python3 server.py`
3. Start peer 1 with its folder/name: `python3 peer.py localhost --rfc-dir peer1_rfcs --peer-name peer1.local`
4. Start peer 2 with another folder/name: `python3 peer.py localhost --rfc-dir peer2_rfcs --peer-name peer2.local`
5. Use the peer CLI (`add`, `lookup`, `list`, `download`) to share and retrieve RFCs. Download-only peers can start with an empty directory and still use `lookup`/`download`.
# CSC573_vkakkal_ymor2_P1
