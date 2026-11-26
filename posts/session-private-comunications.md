---
title: "Session: Privacy Beyond End-to-End Encryption"
date: 2026-11-26
---

Messaging apps have become a fundamental part of how we communicate. WhatsApp alone has more than 3 billion monthly active users. For much of the population, communicating over the internet means relying on platforms controlled by a handful of private companies.

This creates a problem. Companies like Meta operate under economic incentives that do not always align with their users' interests. Their business models rely heavily on advertising and the information they can collect about the people using their services. They don't need to read our conversations to learn a great deal about us.

[End-to-end encryption](https://en.wikipedia.org/wiki/End-to-end_encryption) (E2EE) has been a major step forward. Apps like WhatsApp and Signal use it to prevent intermediaries, including the platforms themselves, from reading the contents of private conversations. But protecting the content of a conversation is not the same as protecting all the information surrounding it. Who talks to whom, when, and from where can reveal just as much as the messages themselves.

Meanwhile, governments continue pushing to expand their surveillance capabilities over private communications, with the clear intention of extending mass surveillance over citizens and political dissidents. In Europe, proposals commonly known as [Chat Control](https://fightchatcontrol.eu/) have raised the possibility of introducing mechanisms to scan private communications under the pretext of combating child sexual abuse.

> It was never about the children.

There are more than just political interests behind these proposals. Organizations developing surveillance and content-scanning technologies have been actively lobbying for them, alongside major tech companies like Meta, which has also been a major advocate of age verification.

Privacy should not depend on trusting a company or a government to respect it. It should be a property of the system itself.

Fortunately, there are alternatives designed to address this problem at the architectural level. Signal, SimpleX, and Session take different approaches to minimizing the information that intermediaries can collect about their users.

In this post, I'll focus on **Session**, an open-source messenger that combines end-to-end encryption, a decentralized network of nodes, and onion routing to minimize metadata exposure.

I hadn't used Session myself, so I decided to read its [whitepaper](https://arxiv.org/pdf/2002.04609) and look into how its infrastructure works.

## How Session works

![session-architecture](/img/posts/session-private-communications/session-architecture.webp)

Unlike WhatsApp and Signal, Session does not require a phone number, email address, or any other personal information to create an account. Instead, accounts are identified by public keys, with no central authority responsible for registering or managing identities.

Account generation is deterministic. The client generates 16 bytes (128 bits) of cryptographically secure randomness, which are encoded into a 13-word recovery phrase. This phrase allows users to recover their identity on another device without relying on a central server.

From this seed, Session derives an [Ed25519](https://en.wikipedia.org/wiki/EdDSA#Ed25519) key pair for digital signatures. The Ed25519 keys are then converted into an X25519 key pair, which is used for Diffie-Hellman key agreement. Both pairs are derived from the same original seed, but serve different purposes: Ed25519 authenticates messages, while X25519 allows the parties to establish the cryptographic secrets needed for encryption.

The final component is the **Account ID**, the public identifier used to identify an account on the Session network. It consists of a one-byte prefix (`0x05`) followed by the user's 32-byte X25519 public key:

`Account ID = 0x05 || pk_X25519`

The result is a 66-character hexadecimal identifier. Anyone who knows your Account ID also knows your X25519 public key, but cannot derive your private key from it.

### How messages are encrypted

To understand how these keys are used, consider a simple example: Alice wants to send an encrypted message to Bob.

Alice first needs Bob's Account ID, from which she extracts his X25519 public key. She then generates a fresh, ephemeral X25519 key pair for the message and performs an Elliptic-Curve Diffie-Hellman (ECDH) operation using her ephemeral private key and Bob's public key.

This produces a shared secret:

`S = X25519(sk_A_ephemeral, pk_B)`

The secret is used to derive the symmetric key needed to encrypt the message. Before encryption, Alice also signs the message and the relevant identity information using her Ed25519 private key. The signature, her signing public key, and the message are then encrypted using authenticated symmetric encryption.

Alice sends the resulting ciphertext together with her ephemeral X25519 public key. Her ephemeral private key is never transmitted.

When Bob receives the message, he performs the corresponding Diffie-Hellman operation using his own private X25519 key and Alice's ephemeral public key:

`S = X25519(sk_B, pk_A_ephemeral)`

Both operations produce the same shared secret. Bob can therefore derive the same symmetric encryption key, decrypt the message, and verify Alice's Ed25519 signature.

Neither Alice nor Bob needs to exchange private keys, and Bob does not even need to be online when Alice encrypts the message.

There is, however, an important limitation. In Session Protocol V1, Bob's long-term private key is involved in decrypting every message sent to his account. If that key is compromised, an attacker who has stored previous ciphertexts can potentially decrypt them. **Session V1 does not provide Perfect Forward Secrecy**, a limitation that Session Protocol V2 is designed to address.

This explains how Session protects message content, but not how those messages reach their recipients. For that, Session relies on a decentralized network of servers responsible for routing and temporarily storing encrypted messages.

### Nodes

Knowing Bob's public key is enough for Alice to encrypt a message, but it does not tell her where to send it. An Account ID is a cryptographic identifier, not an IP address.

In a purely peer-to-peer system without intermediate infrastructure, Alice would need to discover Bob's network address and establish a direct connection with his device. This would also require Bob to be online when Alice sends the message, unless another system temporarily holds it for him.

Session avoids this by relying on the **Session Network**, a decentralized infrastructure of servers called Session Nodes.

These nodes are operated by independent participants rather than a single company. They provide the infrastructure needed to route requests, temporarily store encrypted messages, and make them available when recipients reconnect.

A Session Node performs several roles within the network. It can forward encrypted requests, participate in message storage and replication, and help maintain the network's state, including information about active nodes and their responsibilities.

Session also uses a dedicated blockchain, known as the Session Appchain, to coordinate parts of the network's state, consensus, and reward mechanisms. This does not mean messages are stored on a blockchain. The actual message data remains on the storage servers.

When a client first connects, it uses a set of predefined bootstrap nodes to discover the network. From there, it can obtain information about participating Session Nodes and determine which servers are responsible for a given Account ID.

The important distinction is that the nodes do not need access to users' private keys or plaintext messages to perform these tasks. Alice encrypts her message before sending it to the infrastructure, and Bob decrypts it locally after retrieving it.

This separates the infrastructure responsible for delivering messages from the users communicating through it.

But running servers costs money. Operators need hardware, bandwidth, storage, and a reliable connection. Session therefore needs an incentive mechanism that makes operating nodes economically viable while discouraging malicious participants from controlling large parts of the network.

### Tokenomics

Session uses an economic incentive model based on **Session Token (SESH)**, an EVM-compatible token used for staking and network rewards.

To register a Session Node, an operator must lock 25,000 SESH through a staking smart contract. The operator can provide the full amount or contribute at least 25% of the requirement (6,250 SESH), allowing other participants to supply the remaining tokens. A node can have up to ten contributors, including the operator.

This allows people to contribute capital without necessarily operating a server themselves. In return, operators and contributors receive rewards for participating in the network.

SESH operates within the Ethereum ecosystem, with staking and reward contracts deployed on **Arbitrum One**, a Layer 2 network that reduces transaction costs compared with Ethereum mainnet.

The Session Appchain handles frequent network coordination tasks, while the EVM contracts manage the economic side of participation. Keeping these functions separate avoids placing message delivery or every network operation directly on Ethereum.

The reason for requiring staking is not simply to compensate node operators. It also introduces a financial cost to a [Sybil attack](https://en.wikipedia.org/wiki/Sybil_attack).

In a network where anyone can create an unlimited number of node identities without committing resources, an attacker could deploy thousands of servers and attempt to control a significant portion of the infrastructure.

Session makes this more expensive.

For example, registering 500 nodes would require locking 12.5 million SESH, in addition to the costs of running those servers.

This does not make the network immune to Sybil attacks. It means that controlling large numbers of nodes requires a significant economic commitment.

The effectiveness of this mechanism depends on the distribution of tokens, the independence of node operators, the cost of acquiring SESH, and the rules used to assign nodes to the network.

A network with thousands of servers is not necessarily decentralized if most of them belong to a handful of operators.

#### Network rewards

Node rewards come from the **Staking Reward Pool**, a reserve of tokens distributed among active and eligible Session Nodes.

At launch, approximately 63.18 million SESH were allocated to this pool. The economic model targets an annual release of 14% of the remaining reward pool, with rewards distributed across active nodes.

This is not a guaranteed 14% annual return for stakers. Each node's reward depends on the size of the pool and how many other nodes are participating.

The network also aims to replenish its reward pool through fees associated with premium features, such as Session Pro and Session Names.

In August 2026, Session proposed separating Pro subscription revenue used to finance application development from the fees paid to compensate the network for the resources consumed by Pro users. This distinction matters: sustaining the infrastructure and financing the software itself are two different problems.

The resulting model attempts to align the incentives of users, node operators, and contributors. Whether it can remain economically sustainable over the long term is another question.

For more details, see the [Session tokenomics documentation](https://docs.getsession.org/session-token-sesh/tokenomics) and the [2026 Session Pro proposal](https://getsession.org/blog/session-pro-tokenomics-proposal).

### Onion Requests

We now have a decentralized network capable of delivering encrypted messages. But another problem remains: how does Alice communicate with a Session Node without revealing her IP address to the server storing Bob's messages?

If Alice connected directly to Bob's storage server, that server could observe her IP address and the Account ID associated with the storage request.

Even though it could not decrypt the message, it could potentially associate Alice's network connection with activity involving Bob's account.

Session addresses this using **Onion Requests**, a routing protocol based on the same general principle as Tor's onion routing.

Instead of connecting directly to the destination server, the client sends its request through a path of three Session Nodes. Each node receives an encrypted layer containing only the information needed to forward the request to the next hop.

Consider the following path:

`Alice → Guard → Middle → Exit → Destination`

The destination is a Session Node responsible for handling Alice's request, such as a member of Bob's swarm.

To build the request, Alice first prepares the operation she wants the destination to execute. This could be a request to store an encrypted message or retrieve previously stored data.

She then encrypts the destination request and wraps it in additional layers of encryption, working backwards through the selected path.

Conceptually:

`Onion = Enc_G(Next=M, Enc_M(Next=E, Enc_E(Destination, EncryptedRequest)))`

This is a simplified representation of the protocol, not its exact binary format.

Each node uses its private key and the cryptographic information included in the request to remove the layer intended for it.

The **Guard Node** receives the original connection from Alice. It can observe her IP address, but it only learns which middle node should receive the remaining encrypted request.

The **Middle Node** sees a request arriving from the guard and knows which exit node should receive it next. It does not need to know Alice's IP address or the final destination.

The **Exit Node** removes its layer and forwards the remaining encrypted request to the destination server. It knows where the request must go, but not Alice's original IP address.

Finally, the destination processes the request and sends its response back through the route.

The result is that no individual node on the path needs to know both the origin and final destination of the communication.

There is also an important distinction between the two encryption layers involved.

End-to-end encryption protects the message content. Onion routing protects the transport of the request.

When Alice sends a message, the destination server may decrypt the onion request to process the storage operation, but the actual message remains encrypted for Bob.

Session clients also maintain persistent entry nodes, known as guards, rather than selecting completely new entry points for every request. This limits how frequently a client exposes its IP address to different operators, although compromised guards can observe activity for longer.

Onion Requests reduce the metadata available to individual servers. They do not make traffic analysis impossible, especially against an adversary capable of observing or controlling multiple points in the network.

For a more detailed explanation, see the [Onion Requests documentation](https://docs.getsession.org/session-network/session-protocol/onion-requests-and-message-routing).

### Storage

We have reached the final part of the message's journey.

Alice has encrypted her message and sent it through an onion request. But Bob may still be offline. Session needs somewhere to hold the ciphertext until he connects.

This is the purpose of **swarms**.

A swarm is a small group of Session Nodes responsible for temporarily storing encrypted messages associated with a range of Account IDs.

Swarms typically contain around five to seven nodes. Each node maintains redundant copies of the messages assigned to its swarm, allowing the system to continue functioning when individual servers become unavailable.

Unlike a blockchain, Session does not replicate every message across the entire network. Only the nodes responsible for a particular account need to store its messages.

#### How accounts are assigned to swarms

The assignment is deterministic.

The original Session architecture describes a 64-bit identifier space used to distribute accounts among swarms. An Account ID is mapped into this space, and the responsible swarm is selected according to the proximity of the corresponding identifiers.

The practical consequence is that an Account ID determines which group of servers is responsible for its temporary storage, given the current network state.

This does not mean every user gets a separate swarm. The same swarm can store encrypted messages for many different accounts.

When Alice wants to send a message to Bob, her client requests the current swarm mapping for Bob's Account ID.

Suppose Bob's swarm contains five nodes:

`Bob's swarm = {S1, S2, S3, S4, S5}`

Alice selects one of these nodes and sends the encrypted message using an Onion Request.

The receiving node validates the storage operation and propagates the message to the remaining members of the swarm.

Each node stores a copy of the encrypted payload together with the metadata required to manage it, including its destination Account ID, timestamp, namespace, and expiry time.

The important property here is **redundancy**.

If S1 goes offline, Bob may still retrieve the message from S2, S3, S4, or S5. As nodes join and leave the network, swarms are reorganized and their stored records synchronized.

The nodes also have limited influence over the swarms to which they are assigned, making it harder for an attacker to register servers directly into a specific user's swarm.

#### Retrieving messages

Bob does not need to maintain a permanent connection to Alice.

When he opens Session, his client contacts the nodes responsible for his Account ID and checks whether new messages are available.

This process is called *polling*.

The client sends a retrieval request specifying the account and storage namespace it wants to query. It also maintains information about previously retrieved messages to avoid downloading and processing the same data repeatedly.

The server returns the available ciphertexts, which Bob then decrypts and verifies locally.

The original messages have never needed to pass directly between Alice's and Bob's devices.

This separation between sender, recipient, and storage infrastructure is what allows Session to support asynchronous communication without a centralized message server.

#### Message expiration

Storage is temporary.

By default, ordinary messages have a 14-day Time to Live (TTL). Once this period expires, honest nodes remove them from their storage.

Session also uses different *namespaces* to separate categories of data.

For example, namespace `0` stores ordinary direct messages, while other namespaces are used for encrypted profile information, contacts, group configuration, and related application state.

Some configuration data has a longer default TTL of 30 days and can be refreshed by active clients.

This also means the swarm is not a permanent backup of your conversations. Recovering your Account ID using your recovery phrase does not automatically restore messages that have already expired from the network and are no longer present on another device.

File attachments follow a different path. They are encrypted locally and uploaded to separate file servers, while the messages contain the references and cryptographic information needed to retrieve and decrypt them.

The distinction matters: not every part of Session's infrastructure uses exactly the same decentralized storage model.

At this point, we can reconstruct the complete journey of a message:

1. Alice obtains Bob's Account ID and encrypts the message using Session Protocol.
2. Her client discovers the Session Nodes responsible for Bob's swarm.
3. The storage request travels through a three-hop onion route.
4. A node in Bob's swarm receives the ciphertext and replicates it to the other members.
5. Bob later polls his swarm through his own onion route, retrieves the ciphertext, and decrypts it locally.

This is the core of Session's architecture: cryptographic identities, decentralized routing, and distributed temporary storage, operating without requiring users to establish direct connections with one another.

## Security trade-offs and limitations

Session's architecture solves several problems associated with conventional messaging infrastructure, but decentralization does not automatically provide stronger security in every area.

The most important limitation is the absence of **Perfect Forward Secrecy in Session Protocol V1**.

As explained earlier, messages are encrypted using secrets derived from the recipient's long-term private key. If an adversary stores encrypted messages and later compromises that key, the historical messages may become readable.

Session's 14-day storage expiration reduces how long messages should remain available from honest nodes. However, it does not prevent malicious operators or other observers from saving ciphertexts beyond their expiration.

A second limitation concerns metadata.

Onion Requests are designed to prevent any individual relay from learning both the origin and destination of a request, but a sufficiently capable adversary can attempt traffic correlation.

An attacker observing multiple entry and exit points may compare packet sizes, timing, and communication patterns. A global observer with visibility across large parts of the network poses an even more difficult threat.

Session's original whitepaper explicitly acknowledges limitations against global adversaries.

The storage model has its own security assumptions. Replication improves availability, but it does not guarantee that every message will be delivered. A malicious node may discard a message before propagating it to the rest of the swarm.

These are not purely theoretical concerns.

In August 2026, researchers presented [Practical Attacks on a Decentralized Secure Messenger Session](https://www.usenix.org/conference/woot26/presentation/urushigaki) at USENIX WOOT.

Their analysis identified weaknesses in Session Protocol V1 involving public-key authentication and the lack of cryptographically enforced message ordering. They demonstrated attacks involving impersonation, timestamp manipulation, and message dropping or replay under specific conditions.

These findings do not imply that every Session conversation can be read by an attacker. They demonstrate that encrypting individual messages is not sufficient to guarantee every property expected from a secure messaging protocol.

A valid digital signature, for example, proves that someone possesses the corresponding private key. It does not automatically prove that the key belongs to the person a user believes they are communicating with.

There are also limitations outside ordinary text messaging.

Session's current voice and video calls use peer-to-peer connections, which can expose network information to the other participant. File attachments rely on separate infrastructure, while mobile notifications introduce additional operating-system and service dependencies.

Finally, there is the economic question.

Session's decentralization depends on operators continuing to provide infrastructure. The Staking Reward Pool is finite, and its reward emission gradually reduces the number of tokens remaining in the pool unless new tokens are added.

The project intends to supplement these rewards through premium features and network fees, while keeping essential messaging functionality free.

But long-term sustainability depends on whether these mechanisms generate enough economic value to compensate operators and finance the ongoing development of the application.

There is also a distinction between the number of nodes and the number of independent operators. A large network is not necessarily resistant to coordinated attacks if ownership and infrastructure are concentrated.

These limitations do not invalidate Session's architecture. They define the assumptions under which its privacy and security guarantees should be evaluated.

## Session Protocol V2

Session Protocol V2 is the project's attempt to address some of the most important cryptographic limitations of V1.

The upgrade focuses on three areas: **Perfect Forward Secrecy, post-quantum cryptography, and more secure linked-device management**.

Instead of relying on the same long-term encryption key indefinitely, V2 introduces rotating encryption keys for accounts and individual devices.

According to the current design, these keys will rotate approximately every 12 hours, with old keys retained for up to 16 days to allow offline clients to decrypt messages still available in their swarms.

After that period, the old keys are deleted.

This limits the amount of historical ciphertext that can be decrypted after a later compromise of a device. The protection is not instantaneous: messages encrypted with keys that are still retained remain within the exposure window.

V2 also introduces a hybrid cryptographic construction combining **X25519 and ML-KEM-768**.

ML-KEM is a post-quantum key encapsulation mechanism standardized by NIST. Combining it with X25519 is intended to protect encrypted messages even if a future quantum computer can break today's elliptic-curve cryptography.

The design also changes how linked devices are managed. Each device receives its own cryptographic identity, and new devices must be authorized through a verification process.

This removes some of the limitations associated with sharing the same long-term private key across every device linked to a Session account.

As of November 2026, V2 is not yet the default messaging protocol.

The core cryptographic implementation has been completed in `libsession`, and support for recognizing future V2 messages has begun appearing in Session clients. However, device-group management, account migration, integration, and additional security review are still in progress.

The developers also plan to retain compatibility mechanisms for users who have not migrated or whose published keys have expired.

This introduces another security trade-off: maintaining communication with offline or outdated clients may require falling back to weaker encryption guarantees.

Session is also developing a more advanced network transport called Session Router, designed to improve the routing layer and introduce forward-secret, post-quantum protection for network connections.

It is important to separate these improvements. **A stronger onion-routing transport does not replace the need for a secure end-to-end messaging protocol.** Both layers protect different information.

The [October 2026 development update](https://getsession.org/blog/session-protocol-v2-update) provides more details about V2's implementation and remaining work.

For anyone interested in the technical details, I recommend reading the original [whitepaper](https://arxiv.org/pdf/2002.04609), the [current documentation](https://docs.getsession.org/), and the [source code](https://github.com/session-foundation).
