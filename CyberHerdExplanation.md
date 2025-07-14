# Joining the CyberHerd: How It Works

## What is the CyberHerd?

The #CyberHerd is a community of Nostr users who collectively support the ⚡Lightning Goats⚡ project. As a herd member, you'll receive a share of all payments sent to feed the goats every time the feeder is triggered!

## How to Join the CyberHerd

The CyberHerd operates continuously with automatic monitoring of Nostr interactions:

1. **Find the CyberHerd note**: Look for today's note tagged with #CyberHerd
2. **Zap the note**: Send a zap of 10+ sats to join the herd and earn payouts
3. **Instant processing**: Your membership is processed immediately when detected
4. **Notification**: You'll be notified via public reply when you join the herd

**Requirements for membership:**
- Valid NIP-05 identifier (your verified Nostr address)
- Working Lightning address to receive payments
- Zap today's #CyberHerd note with at least 10 sats

**Note**: Only zaps (Kind 9735) are processed for CyberHerd membership.

## How Payouts Work

Every time someone triggers the feeder (by reaching 850 sats in the system balance) and feeds the ⚡Lightning Goats⚡, 10% of the trigger amount is split among all CyberHerd members:

- **Zap-only membership**: Only zaps of 10+ sats qualify for CyberHerd membership
- **Proportional payouts**: Larger zaps = larger share of future payouts
- **Cumulative contributions**: Multiple zaps from the same member are added together, increasing your total contribution and payout share
- **Real payouts**: Payouts depend on feeder activity - no feedings = no payouts, BIG FEEDINGS = BIG PAYOUTS!
- **Limited spots**: Maximum herd size is 3 members
- **Automatic distribution**: Payments are sent directly to your Lightning address when the feeder is triggered

## Payout Calculation Examples

Your payout percentage is calculated based on your total zap contributions:

**Example 1 - Varied contributions:**
- Member A: 1000 sats total → Gets largest share
- Member B: 500 sats total → Gets medium share  
- Member C: 200 sats total → Gets the smallest share

**Example 2 - Building contributions:**
- Initial zap: 200 sats → Your contribution: 200 sats
- Second zap: 300 sats → Your contribution: 500 sats total  
- Third zap: 100 sats → Your contribution: 600 sats total
- Your payout share grows with each additional zap!

## The ⚡Headbutting⚡ Mechanism

When the CyberHerd reaches maximum capacity, new members can still join by "headbutting" existing members:

### How Headbutting Works:
- **Zap requirement**: Only zaps of 10+ sats can trigger headbutting
- **Target selection**: You must exceed the lowest contributing member's total zap amount
- **Automatic process**: If your zap qualifies, the system automatically removes the lowest member
- **Instant replacement**: You immediately take their spot in the herd

### Headbutting Examples:

**Scenario 1 - Basic headbutt:**
- Current herd: members with zap totals of [1000, 500, 200]
- You zap: 250 sats → You replace the 200-sat member
- New herd: [1000, 500, 250] (you're now in the herd)
- The headbutted member's 200 sats are reset to zero

**Scenario 2 - Failed headbutt:**
- Current herd: members with zap totals of [1000, 500, 200 sats]  
- You zap: 150 sats → Headbutt fails (need 201+ sats to exceed 200)
- You get notified of the failure

**Scenario 3 - Existing member zaps more:**
- You're in the herd with 300 sats total
- You zap another 200 sats → Your total becomes 500 sats
- Your payout share increases, harder to get headbutted out

**Scenario 4 - Getting headbutted and rejoining:**
- You're in the herd with 400 sats total
- Someone headbutts you out with 450 sats → You lose your spot AND your previous zap amount is reset to zero
- To rejoin: You must start fresh with a new zap that exceeds the current lowest member
- Your accumulated amount from before getting headbutted is completely reset

### Protection Strategy:
- **Build your total**: Multiple zaps accumulate, making you harder to headbutt
- **Monitor the herd**: Check current members' contributions before zapping
- **Stay active**: Regular zapping increases your "headbutt resistance"
- **Risk awareness**: Getting headbutted means losing ALL accumulated sats - they don't carry over if you rejoin

### Headbutting Rules:
- **Minimum zap**: 10 sats required to attempt headbutting
- **Amount reset**: When headbutted out, your accumulated amount is completely reset to zero
- **Fresh start**: To rejoin after being headbutted, you start with zero sats and must build up again
- **Cooldown period**: 5-second cooldown after each successful headbutt
- **Public notifications**: Both parties receive public reply notifications about headbutts
- **Fair play**: System prevents rapid-fire headbutting attempts

## System Features

### Automatic Monitoring:
- **CyberHerd service**: Continuously monitors Nostr for #CyberHerd interactions
- **Real-time processing**: Immediate membership updates when you zap CyberHerd note
- **Zap-only system**: Only processes Kind 9735 (Zap Receipts) for membership

### Security & Reliability:
- **Transaction safety**: All database operations use atomic transactions
- **Duplicate prevention**: System prevents double-processing of the same zap events
- **Error handling**: Robust error handling with user notifications
- **Cooldown protection**: Prevents spam and ensures fair headbutting

### Notifications:
- **Public replies**: Notifications sent as public replies to #CyberHerd note
- **Headbutt alerts**: Public notifications when you headbutt someone or get headbutted
- **Failure notices**: Public alerts when headbutt attempts fail
- **Status updates**: Public confirmations when you join the herd
- **WebSocket updates**: Real-time updates sent to connected clients

## Getting Started

1. **Set up your profile**: Ensure you have a valid NIP-05 identifier and working Lightning address configured
2. **Find CyberHerd note**: Look for today's #CyberHerd tag by the Lightning Goats project
3. **Zap to join**: Send a zap of 10+ sats to join the herd
4. **Zap for more**: Send larger zaps to increase your payout share and headbutt protection
5. **Monitor the herd**: Check current members to plan your strategy
6. **Stay active**: Regular zaps build up your total contribution and payout share

## Important Notes

- **NIP-05 required**: You must have a valid NIP-05 identifier for membership
- **Zap-only system**: Only zaps count for membership
- **Minimum 10 sats**: Zaps must be at least 10 sats to qualify for membership
- **Cumulative system**: Your zap amounts add up over time, building your contribution
- **Amount reset on headbutt**: If you get headbutted out, your accumulated amount is completely reset to zero
- **Fresh start after headbutt**: Rejoining after being headbutted requires starting over from zero sats
- **Persistent membership**: Once you're in the herd, you stay until headbutted out
- **Lightning required**: You must have a working Lightning address to receive payouts
- **Automated system**: Everything happens automatically via Nostr monitoring
- **Public notifications**: All notifications are sent as public replies to #CyberHerd note
- **Bug potential**: This is hobby project code - expect occasional issues!
