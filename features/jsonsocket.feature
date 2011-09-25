#@PydevCodeAnalysisIgnore
Feature: Test Server
	Scenario: Start Server
		Given I start the server
		Given I connect the client
		When the client sends the object {"message": "new connection"}

		Then I see a connection
		
	Scenario: Server Response
		When the server sends the object {"message": "welcome"}
		Then the client sees a message {"message": "welcome"}
		
	Scenario: Stop Server
		Given I stop the server
		Then I see a stopped server
		Then I close the client
