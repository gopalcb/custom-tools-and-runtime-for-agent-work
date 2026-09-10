import { Component, input, output } from '@angular/core';
import { Skill } from '../../shared-services/interfaces';
@Component({ selector:'app-skill-card', standalone:true, templateUrl:'./skill-card.component.html', styleUrl:'./skill-card.component.css' })
export class SkillCardComponent { readonly skill=input.required<Skill>(); readonly selected=input(false); readonly skillSelected=output<string>(); }
