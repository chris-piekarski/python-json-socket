#@PydevCodeAnalysisIgnore
Feature: Timeout Behavior

  Scenario: Stop server despite long accept timeout
    Given I start the server with accept timeout 10.0 seconds
    When I stop the server
    Then the server is stopped

  Scenario: Separate accept and recv timeouts
    Given I start the server with accept timeout 10.0 seconds and recv timeout 0.2 seconds
    And I connect the client
    When I wait 0.3 seconds
    And the client sends the object {"echo": "after-idle"}
    Then the client sees a message {"echo": "after-idle"}
