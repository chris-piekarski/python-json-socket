#@PydevCodeAnalysisIgnore
Feature: Test Server

  Background:
    Given I start the server
    And I connect the client

  Scenario: Start Server
    When the client sends the object {"message": "new connection"}
    Then within 2 seconds the server is connected

  Scenario: Server Response
    When the server sends the object {"message": "welcome"}
    Then the client sees a message {"message": "welcome"}

  Scenario: Stop Server
    Given I stop the server
    Then the server is stopped
    And I close the client

  Scenario: Accepts second client after first disconnects
    Given I disconnect the client
    And I connect a new client
    When the client sends the object {"echo": "two"}
    Then the client sees a message {"echo": "two"}

  Scenario: Client read fails after server stops
    Given I stop the server
    Then the server is stopped
    When the client attempts to read with timeout 1.0 seconds
    Then the client read fails with timeout or disconnect
