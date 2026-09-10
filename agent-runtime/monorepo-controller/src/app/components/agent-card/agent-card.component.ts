import { Component, input, output } from '@angular/core';
import { Agent } from '../../shared-services/interfaces';
@Component({ selector:'app-agent-card', standalone:true, templateUrl:'./agent-card.component.html', styleUrl:'./agent-card.component.css' })
export class AgentCardComponent { readonly agent = input.required<Agent>(); readonly selected = input(false); readonly agentSelected = output<string>(); }
