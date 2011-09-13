#@PydevCodeAnalysisIgnore
Feature: Test Server
	Scenario: Start Server
		Given I start the server
		Given I connect the client
		When I send the object {"message": "new connection"}

		Then I see a connection
		
	Scenario: Stop Server
		Given I stop the server
		Then I see a stopped server
