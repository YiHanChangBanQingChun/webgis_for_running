package dev.runningatlas.api;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class RunningWebgisApiApplication {

	public static void main(String[] args) {
		SpringApplication.run(RunningWebgisApiApplication.class, args);
	}

}
