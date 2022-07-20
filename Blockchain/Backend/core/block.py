""" 
Copyright (c) 2021 Codiesalert.com
These scripts should be used for commercial purpose without Codies Alert Permission
Any violations may lead to legal action
"""
from Blockchain.Backend.core.blockheader import BlockHeader
from Blockchain.Backend.core.Tx import Tx
from Blockchain.Backend.util.util import (little_endian_to_int, int_to_little_endian, encode_varint, read_varint)
class Block:
    """
    Block is a storage containter that stores transactions
    """
    command = b'block'

    def __init__(self, Height, Blocksize, BlockHeader, TxCount, Txs):
        self.Height = Height
        self.Blocksize = Blocksize
        self.BlockHeader = BlockHeader
        self.Txcount = TxCount
        self.Txs = Txs

    @classmethod
    def parse(cls, s):
        Height = little_endian_to_int(s.read(4))
        BlockSize = little_endian_to_int(s.read(4))
        blockHeader = BlockHeader.parse(s)
        numTxs = read_varint(s)

        Txs = []

        for _ in range(numTxs):
            Txs.append(Tx.parse(s))

        return cls(Height, BlockSize, blockHeader, numTxs, Txs)
        
    def serialize(self):
        result = int_to_little_endian(self.Height, 4)
        result += int_to_little_endian(self.Blocksize, 4)
        result += self.BlockHeader.serialize()
        result += encode_varint(len(self.Txs))

        for tx in self.Txs:
            result += tx.serialize()
        
        return result 

    @classmethod
    def to_obj(cls, lastblock):
        block = BlockHeader(lastblock['BlockHeader']['version'],
                    bytes.fromhex(lastblock['BlockHeader']['prevBlockHash']),
                    bytes.fromhex(lastblock['BlockHeader']['merkleRoot']),
                    lastblock['BlockHeader']['timestamp'],
                    bytes.fromhex(lastblock['BlockHeader']['bits']))
        
        block.nonce = int_to_little_endian(lastblock['BlockHeader']['nonce'], 4)

        Transactions = []
        for tx in lastblock['Txs']:
            Transactions.append(Tx.to_obj(tx))
        
        block.BlockHash = bytes.fromhex(lastblock['BlockHeader']['blockHash'])
        return cls(lastblock['Height'], lastblock['Blocksize'], block, len(Transactions), Transactions)

    def to_dict(self):
        dt = self.__dict__
        self.BlockHeader = self.BlockHeader.to_dict()
        return dt
