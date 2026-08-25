# Requirements Document

## Introduction

This feature is a Python simulation of a simple electronic exchange limit order book and matching engine. It models the core behavior of a continuous double-auction market: incoming buy and sell orders are matched against resting orders on the opposite side of the book using price-time priority. The system supports limit and market orders, order cancellation by identifier, trade recording, and inspection of the current top of book. A command-line interface allows a user to interact with the engine directly.

The design goal is clarity and correctness suitable for explanation in a software engineering interview, not exhaustive exchange feature coverage. Dependencies are kept minimal and the codebase is organized into logical modules (orders, order book, matching engine, trades, CLI, and tests). Order_Identifiers are simple monotonically increasing integers starting from 1. Explicitly out of scope: web frontend, authentication, cloud infrastructure, AI features, and speculative abstractions.

## Glossary

- **Matching_Engine**: The component that accepts incoming orders, applies matching rules, produces trades, and mutates the order book.
- **Order_Book**: The data structure holding all resting (unmatched or partially matched) limit orders, organized by side and price level.
- **Order**: A single instruction to buy or sell a quantity of the instrument, identified by a unique order identifier. An order has a side, a type, a quantity, and (for limit orders) a limit price.
- **Side**: The direction of an order, either Buy or Sell.
- **Buy**: A Side value indicating intent to purchase; buy orders match against resting sell orders.
- **Sell**: A Side value indicating intent to sell; sell orders match against resting buy orders.
- **Limit_Order**: An Order that specifies a limit price and may only execute at that price or better.
- **Market_Order**: An Order without a limit price that executes against the best available resting orders on the opposite side until filled or the book is exhausted.
- **Price_Time_Priority**: The matching rule that prioritizes orders first by best price, then, within the same price level, by earliest arrival time.
- **Best_Bid**: The highest limit price among resting buy orders.
- **Best_Ask**: The lowest limit price among resting sell orders.
- **Top_Of_Book**: The current Best_Bid and Best_Ask, each with the aggregate resting quantity available at that price level.
- **Trade**: A record of a completed match between an incoming order and a resting order, capturing the execution price, quantity, the two participating order identifiers, and the aggressor side.
- **Aggressor**: The incoming order that initiates a match against resting orders.
- **Resting_Order**: A limit order that remains in the Order_Book awaiting a match.
- **Remaining_Quantity**: The unfilled quantity of an order after any partial or complete executions.
- **Order_Identifier**: A unique value assigned to each accepted order, used for cancellation and trade records.
- **CLI**: The command-line interface through which a user submits orders, cancels orders, and views state.

## Requirements

### Requirement 1: Submit Buy and Sell Orders

**User Story:** As a market participant, I want to submit buy and sell orders, so that I can express my intent to trade the instrument.

#### Acceptance Criteria

1. WHEN a Buy order with a Remaining_Quantity greater than 0 is submitted, where a Limit_Order additionally carries a Limit_Price greater than 0 and a Market_Order carries no Limit_Price, THE Matching_Engine SHALL accept the order, assign a unique Order_Identifier, and return an acknowledgement containing the Order_Identifier.
2. WHEN a Sell order with a Remaining_Quantity greater than 0 is submitted, where a Limit_Order additionally carries a Limit_Price greater than 0 and a Market_Order carries no Limit_Price, THE Matching_Engine SHALL accept the order, assign a unique Order_Identifier, and return an acknowledgement containing the Order_Identifier.
3. IF an order is submitted with a Remaining_Quantity less than or equal to 0, THEN THE Matching_Engine SHALL reject the order, return a validation error indicating that Remaining_Quantity must be a positive integer, and preserve the order book without adding the order.
4. IF an order is submitted with a Side field whose value is not exactly "Buy" or "Sell", THEN THE Matching_Engine SHALL reject the order, return a validation error indicating an invalid Side value, and preserve the order book without adding the order.
5. IF a Limit_Order is submitted with a Limit_Price less than or equal to 0, THEN THE Matching_Engine SHALL reject the order, return a validation error indicating that Limit_Price must be a positive price greater than 0, and preserve the order book without adding the order.
6. THE Matching_Engine SHALL assign each accepted order an Order_Identifier that is a monotonically increasing integer starting at 1 and distinct from every Order_Identifier assigned during the current engine session.
7. IF a Limit_Order is submitted with a required field (Side, Limit_Price, or Remaining_Quantity) missing or null, or a Market_Order is submitted with a required field (Side or Remaining_Quantity) missing or null, THEN THE Matching_Engine SHALL reject the order, return a validation error identifying the missing field, and preserve the order book without adding the order.

### Requirement 2: Support Limit and Market Orders

**User Story:** As a market participant, I want to submit both limit orders and market orders, so that I can control price or prioritize immediate execution.

#### Acceptance Criteria

1. WHEN a Limit_Order is submitted with a limit price greater than 0 and a quantity that is a positive integer, THE Matching_Engine SHALL accept the order for matching.
2. IF a Limit_Order is submitted with a limit price less than or equal to 0, THEN THE Matching_Engine SHALL reject the order, leave the Order_Book unchanged, and return a validation error indicating that the limit price must be a positive price greater than 0.
3. IF a Limit_Order is submitted with a quantity that is not a positive integer, THEN THE Matching_Engine SHALL reject the order, leave the Order_Book unchanged, and return a validation error indicating that the quantity must be a positive integer.
4. WHEN a Market_Order is submitted with a quantity that is a positive integer, THE Matching_Engine SHALL match the order against Resting_Orders on the opposite side in price-time priority without applying a limit price constraint.
5. IF a Market_Order is submitted with a quantity that is not a positive integer, THEN THE Matching_Engine SHALL reject the order, leave the Order_Book unchanged, and return a validation error indicating that the quantity must be a positive integer.
6. WHERE a Market_Order cannot be fully filled because no Resting_Orders remain on the opposite side, THE Matching_Engine SHALL fill the available quantity, discard the unfilled Remaining_Quantity, refrain from adding the order to the Order_Book, and return a result indicating the filled quantity and the discarded Remaining_Quantity.
7. WHEN a Limit_Order is submitted and its Remaining_Quantity is greater than 0 after matching against all eligible Resting_Orders, THE Matching_Engine SHALL add only the Limit_Order Remaining_Quantity to the Order_Book as a Resting_Order at the submitted limit price, and no Market_Order SHALL rest in the Order_Book.

### Requirement 3: Match Orders Using Price-Time Priority

**User Story:** As a market participant, I want incoming orders matched by price-time priority, so that matching is fair and predictable.

#### Acceptance Criteria

1. WHEN an incoming Buy order is matched, THE Matching_Engine SHALL match against resting Sell orders in ascending price order, selecting the lowest-priced Resting_Order first.
2. WHEN an incoming Sell order is matched, THE Matching_Engine SHALL match against resting Buy orders in descending price order, selecting the highest-priced Resting_Order first.
3. WHILE multiple Resting_Orders exist at the same price level, THE Matching_Engine SHALL match the Resting_Order with the earliest arrival time first, where arrival time is determined by the order in which the Matching_Engine accepted the orders.
4. IF an incoming Limit_Order Buy has a limit price below the Best_Ask, THEN THE Matching_Engine SHALL not execute any match for that order and SHALL rest the Limit_Order in the Order_Book.
5. IF an incoming Limit_Order Sell has a limit price above the Best_Bid, THEN THE Matching_Engine SHALL not execute any match for that order and SHALL rest the Limit_Order in the Order_Book.
6. WHEN a match occurs, THE Matching_Engine SHALL set the execution price to the limit price of the Resting_Order.
7. WHEN a match occurs, THE Matching_Engine SHALL set the matched quantity to the smaller of the incoming order Remaining_Quantity and the Resting_Order Remaining_Quantity, and SHALL reduce both the incoming order Remaining_Quantity and the Resting_Order Remaining_Quantity by that matched quantity.
8. WHEN the incoming order Remaining_Quantity is smaller than the matched Resting_Order Remaining_Quantity, THE Matching_Engine SHALL partially fill the Resting_Order, retain the Resting_Order in the Order_Book with its reduced Remaining_Quantity, and set the incoming order Remaining_Quantity to zero.
9. WHEN a Resting_Order Remaining_Quantity is smaller than or equal to the incoming order Remaining_Quantity, THE Matching_Engine SHALL fully fill the Resting_Order, remove the Resting_Order from the Order_Book, and continue matching the incoming order against the next price-eligible Resting_Order.
10. WHEN a Resting_Order Remaining_Quantity reaches zero, THE Matching_Engine SHALL remove the Resting_Order from the Order_Book.
11. WHILE matching an incoming order, THE Matching_Engine SHALL continue matching against successive Resting_Orders until either the incoming order Remaining_Quantity reaches zero or no price-eligible Resting_Order remains on the opposite side of the Order_Book.
12. IF no price-eligible Resting_Order exists on the opposite side of the Order_Book, THEN THE Matching_Engine SHALL execute no match for the incoming order.

### Requirement 4: Cancel Orders by Identifier

**User Story:** As a market participant, I want to cancel a resting order by its identifier, so that I can withdraw an order I no longer want executed.

#### Acceptance Criteria

1. WHEN a cancellation is requested for an Order_Identifier that matches exactly one Resting_Order in the Order_Book, THE Matching_Engine SHALL remove that Resting_Order from the Order_Book and return a success response containing the cancelled Order_Identifier and the Remaining_Quantity that was removed.
2. IF a cancellation is requested for an Order_Identifier that does not match any Resting_Order in the Order_Book, THEN THE Matching_Engine SHALL leave the Order_Book unchanged and return a rejection response indicating that the order was not found.
3. IF a cancellation is requested for an Order_Identifier that is empty, malformed, or does not conform to the defined Order_Identifier format, THEN THE Matching_Engine SHALL leave the Order_Book unchanged and return a rejection response indicating that the identifier is invalid.
4. WHEN a Resting_Order is cancelled, THE Matching_Engine SHALL exclude the cancelled order from all subsequent matching such that no Trade is generated against the cancelled Order_Identifier after the success response is returned.
5. WHEN a partially filled Resting_Order is cancelled, THE Matching_Engine SHALL remove only the Remaining_Quantity from the Order_Book, retain all previously recorded Trades associated with that Order_Identifier without modification, and return a success response containing the Remaining_Quantity that was removed.

### Requirement 5: Record Completed Trades

**User Story:** As a market participant, I want completed trades recorded, so that I can review execution history.

#### Acceptance Criteria

1. WHEN a match occurs, THE Matching_Engine SHALL create a Trade recording the execution price, the matched quantity, the Aggressor Order_Identifier, the Resting_Order Order_Identifier, the Aggressor Side, and a monotonically increasing Trade_Identifier that is unique across all recorded Trades.
2. WHEN a match occurs, THE Matching_Engine SHALL record a timestamp on the Trade representing the moment the match was executed.
3. WHEN an incoming order matches multiple Resting_Orders, THE Matching_Engine SHALL create one Trade per Resting_Order matched, ordered by the sequence in which each Resting_Order was matched.
4. THE Matching_Engine SHALL retain all recorded Trades in ascending order of the sequence in which the Trades occurred.
5. WHEN the trade history is requested and at least one Trade has been recorded, THE Matching_Engine SHALL return all recorded Trades in ascending order of occurrence.
6. WHEN the trade history is requested and no Trades have been recorded, THE Matching_Engine SHALL return an empty collection.

### Requirement 6: View Best Bids and Asks

**User Story:** As a market participant, I want to view the current best bids and asks, so that I can assess the state of the market before trading.

#### Acceptance Criteria

1. WHEN the Top_Of_Book is requested, THE Matching_Engine SHALL return the Best_Bid price (the highest resting Buy order price) with its aggregate resting quantity.
2. WHEN the Top_Of_Book is requested, THE Matching_Engine SHALL return the Best_Ask price (the lowest resting Sell order price) with its aggregate resting quantity.
3. IF no resting Buy orders exist WHEN the Top_Of_Book is requested, THEN THE Matching_Engine SHALL return a Best_Bid indicator with a null price and a zero aggregate resting quantity, without raising an error.
4. IF no resting Sell orders exist WHEN the Top_Of_Book is requested, THEN THE Matching_Engine SHALL return a Best_Ask indicator with a null price and a zero aggregate resting quantity, without raising an error.
5. WHEN multiple Resting_Orders exist at the Best_Bid or Best_Ask price level, THE Matching_Engine SHALL report the arithmetic sum of their Remaining_Quantities as the aggregate resting quantity at that level.
6. WHEN exactly one Resting_Order exists at the Best_Bid or Best_Ask price level, THE Matching_Engine SHALL report that single order's Remaining_Quantity as the aggregate resting quantity at that level.

### Requirement 7: Command-Line Interface

**User Story:** As a user, I want a command-line interface to the engine, so that I can submit orders, cancel orders, and view state interactively.

#### Acceptance Criteria

1. WHEN the user enters a command to submit a Limit_Order with a Side, a quantity, and a price and the Matching_Engine accepts the order, THE CLI SHALL display the assigned Order_Identifier.
2. WHEN the user enters a command to submit a Market_Order with a Side and a quantity and the Matching_Engine accepts the order, THE CLI SHALL display each resulting Trade with its execution price and matched quantity, and SHALL display an indication of any unfilled quantity that was discarded.
3. WHEN the user enters a command to cancel an order with an Order_Identifier and the Matching_Engine reports success, THE CLI SHALL display a confirmation identifying the cancelled Order_Identifier.
4. WHEN the user enters a command to view the Top_Of_Book, THE CLI SHALL display the Best_Bid and the Best_Ask each with its aggregate resting quantity, and IF no resting Buy orders or no resting Sell orders exist, THEN THE CLI SHALL display an indication that the corresponding Best_Bid or Best_Ask is unavailable.
5. WHEN the user enters a command to view trade history, THE CLI SHALL display all recorded Trades in the order they occurred, and IF no Trades have been recorded, THEN THE CLI SHALL display an indication that the trade history is empty.
6. IF the user enters an unrecognized command, THEN THE CLI SHALL display an error message indicating the command is not recognized and SHALL display the list of supported commands.
7. IF the user enters a command with missing or malformed arguments, THEN THE CLI SHALL display a usage message for that command indicating the expected arguments and SHALL not forward the command to the Matching_Engine.
8. WHEN the user enters a command to exit, THE CLI SHALL terminate the session.
9. IF the user submits an order and the Matching_Engine rejects it with a validation error, THEN THE CLI SHALL display an error message indicating the reason for rejection and SHALL not display an Order_Identifier.
10. IF the user requests cancellation of an Order_Identifier that the Matching_Engine reports as not found, THEN THE CLI SHALL display a message indicating that no order with that Order_Identifier exists.

### Requirement 8: Unit Tests for Matching Behavior

**User Story:** As a developer, I want clear unit tests for the matching behavior, so that I can verify correctness and explain the logic with confidence.

#### Acceptance Criteria

1. THE test suite SHALL include a test verifying that when a Buy Limit_Order and a Sell Limit_Order have crossing prices (the Buy limit price is greater than or equal to the Sell limit price), exactly one Trade is produced with an execution price equal to the Resting_Order limit price and a matched quantity equal to the smaller of the two order quantities.
2. THE test suite SHALL include a test verifying that when two or more Resting_Orders exist at the same price level, an incoming Aggressor matches the Resting_Order with the earliest arrival time first, producing Trades whose Resting_Order Order_Identifiers appear in ascending arrival-time order.
3. THE test suite SHALL include a test verifying that an incoming order whose quantity exceeds a single Resting_Order quantity produces one Trade per matched Resting_Order, with the count of Trades equal to the number of Resting_Orders consumed.
4. THE test suite SHALL include a test verifying that when an incoming Limit_Order is partially filled, its unfilled Remaining_Quantity is added to the Order_Book as a Resting_Order and is retrievable with a Remaining_Quantity equal to the submitted quantity minus the total matched quantity.
5. THE test suite SHALL include a test verifying that a Market_Order matches against the best available Resting_Orders until filled or the opposite side is exhausted, and that any unfilled Remaining_Quantity is discarded and not added to the Order_Book.
6. THE test suite SHALL include a test verifying that after a Resting_Order is cancelled, a subsequent incoming order that would otherwise have matched it produces no Trade against the cancelled order.
7. THE test suite SHALL include a test verifying that the Top_Of_Book reports the Best_Bid price, the Best_Ask price, and the aggregate Remaining_Quantity at each level equal to the sum of the Remaining_Quantities of all Resting_Orders at that price level.
8. THE test suite SHALL include a test verifying that an incoming Buy Limit_Order priced below the Best_Ask produces zero Trades and is added to the Order_Book as a Resting_Order.
9. THE test suite SHALL assert each verified behavior against observable Matching_Engine outputs, comprising the recorded Trades, the resulting Order_Book Resting_Orders, and the reported Top_Of_Book.
