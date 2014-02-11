#!/usr/bin/env python

import sys
import socket
import json
import SocketServer
import subprocess
import threading
import os

LOCK_SUCCESS = 0
LOCK_FAILURE = 1
LOCK_WAIT = 3

UNLOCK_SUCCESS = 0
UNLOCK_FAILURE = 1

backlog = 10
maxbuf = 10240

paxos_config_file = open("paxos_group_config.json", "r")
paxos_config = json.loads(paxos_config_file.read())

class Commander:

    def __init__(self, leader_id, commander_id, proposal):
        
        # network state
        self.commander_address = tuple(paxos_config["commanders"][commander_id])
        self.leader_id = leader_id

        # Paxos state
        self.commander_id = commander_id
        self.proposal = proposal

    def generate_p2a(self):
        p2a_msg = {"type" : "p2a",
                    "leader_id" : self.commander_id,
                    "proposal" : self.proposal
                  }
        return p2a_msg

    def generate_decision(self):
        adopted_msg = {"type" : "decision",
                        "slot_num" : self.proposal["slot_num"],
                        "proposal_value" : self.proposal["proposal_value"]
                      }
        return adopted_msg

    def generate_preempted(self, ballot_num):
        preempted_msg = {"type" : "preempted",
                        "ballot_num" : ballot_num
                        }
        return preempted_msg


    def send_p2a(self, acceptor_id):
        # create accceptor socket
        acceptor_address = tuple(paxos_config["acceptors"][acceptor_id])
        acceptor_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        acceptor_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        acceptor_sock.connect(acceptor_address)

        # send message to acceptor
        p2a_msg = self.generate_p2a()
        acceptor_sock.sendall(json.dumps(p2a_msg))
        acceptor_sock.close()

    def send_decision(self, replica_id):
        # create accceptor socket
        replica_address = tuple(paxos_config["replicas"][replica_id])
        replica_conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        replica_conn.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        replica_conn.connect(replica_address)

        # send message to acceptor
        decision_msg = self.generate_decision()
        replica_conn.sendall(json.dumps(decision_msg))
        replica_conn.close()
        print "send decision to replica #" + str(replica_id) + " " + str(decision_msg)

    def send_preempted(self, acceptor_ballot_num):
        preempted_msg = self.generate_preempted(acceptor_ballot_num)
        print "ready to send to leader preempted_msg message" + str(preempted_msg)
    
        # connect to leader
        leader_address = tuple(paxos_config["leaders"][self.leader_id])
        leader_conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        leader_conn.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        leader_conn.connect(leader_address)
        # send msg
        leader_conn.sendall(json.dumps(preempted_msg))
        leader_conn.close()

    def send_p2a_recv_p2b(self):

        # create listening socket
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(self.commander_address)
        s.listen(backlog)

        # send p1a to all acceptors
        acceptor_ids = paxos_config["acceptors"].keys()
        for acceptor_id in acceptor_ids:
            print "send p2a to acceptor_id = " + acceptor_id
            self.send_p2a(acceptor_id)

        wait_for_acceptor_ids = acceptor_ids

        # event loop
        while 1:
            # listen for acceptor p1b response
            acceptor_conn, acceptor_address = s.accept()
            data = acceptor_conn.recv(maxbuf).strip()
            if data:
                msg = json.loads(data)
                if msg["type"] == "p2b":
                    acceptor_id = msg["acceptor_id"]
                    acceptor_ballot_num = msg["ballot_num"]
                    print "response from acceptor#" + str(acceptor_id) + " " + str(msg)
                    if acceptor_ballot_num == self.proposal["ballot_num"]:
                        # acceptor adopted leader_ballot_num
                        wait_for_acceptor_ids.remove(acceptor_id)
                        # heard from majority of acceptors
                        if len(wait_for_acceptor_ids) <= len(acceptor_ids) / 2:
                            print "quorum reached"
                            replica_ids = paxos_config["replicas"].keys()
                            for replica_id in replica_ids:
                                print "send decision to replica_id = " + replica_id
                                self.send_decision(replica_id)
                            # completes accept phase
                            return
                    else:
                        # acceptors already adopted a higher leader_ballot_num
                        # accept phase fails
                        preempted_msg = self.generate_preempted(acceptor_ballot_num)
                        self.send_preempted(acceptor_ballot_num)
                        return
                else:
                    print "wrong message received"
            else:
                print "null message received"

            # close connection
            acceptor_conn.close()

    def send_to_leader(self, msg):
        print "ready to send to leader adopte message" + str(msg)

        # connect to leader
        leader_address = tuple(paxos_config["leaders"][self.leader_id])
        leader_conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        leader_conn.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        leader_conn.connect(leader_address)
        # send msg
        leader_conn.sendall(json.dumps(msg))
        leader_conn.close()


if __name__ == "__main__":

    commander_id = sys.argv[1]
    leader_id = sys.argv[2]

    proposal = {"ballot_num" : 3, "slot_num" : 1, "proposal_value" : "lock 1"}
    commander = Commander(leader_id, commander_id, proposal)

    try:
        print "commander #" + commander_id + " started at " + str(commander.commander_address)
        commander.send_p2a_recv_p2b()

    except KeyboardInterrupt:
        print "commander interrupted"
        sys.exit(0)

    print "commander done and exiting"


