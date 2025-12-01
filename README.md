# P2P-CI System Implementation

A simple peer-to-peer system with centralized index for fetching RFCs.

## Components

- `server.py` - Centralized index server (port 7734)
- `peer.py` - P2P peer client with upload/GET capabilities

## Usage

### Start Server
```bash
python3 server.py
```

### Start Peer
Each peer maintains its own RFC directory and a unique hostname identifier. Use
`--rfc-dir` to point the peer at its personal folder (an empty folder is fine for
GET-only peers), `--host` if you need to advertise a host/IP other than
`localhost`, `--default-protocol-version` to choose the protocol token used for
automatic requests (defaults to `PCP-CI/1.0`), and optionally `--peer-name` to
override the advertised hostname (defaults to `<actual-host>-<pid>`):
```bash
python3 peer.py [server_host] --rfc-dir peer1 --peer-name peer1
```
If you omit `--rfc-dir`, the peer defaults to `<peer-name>_rfcs` when
`--peer-name` is supplied, or `<hostname>-<pid>_rfcs` when it is not (where
`<hostname>` is your machine's host name, e.g., `Alienware`). The directory is
created automatically if needed.

### Peer Commands
- `add <rfc_num> <protocol>` - Add RFC to the index (requires `rfc<rfc_num>.txt`; the title is read from the file)
- `lookup <rfc_num> <protocol>` - Find peers with RFC  
- `list <protocol>` - List all RFCs
- `get <rfc_num> <protocol>` - Retrieve RFC from peer (uses that token for both LOOKUP and GET)
- `quit` - Exit

## Protocol Support

- **P2S Protocol**: ADD, LOOKUP, LIST operations between peer and server
- **P2P Protocol**: GET operation for RFC transfers between peers
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
5. Use the peer CLI (`add`, `lookup`, `list`, `get`) to share and retrieve RFCs. GET-only peers can start with an empty directory and still use `lookup`/`get`.
